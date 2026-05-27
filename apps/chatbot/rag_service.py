"""RAG orchestration service.

This module coordinates retrieval from ChromaDB, prompt building and LLM
generation to produce answers, summaries and citations. It keeps
high-level logic out of views and is easy to test and evolve.
"""
from __future__ import annotations

import logging
import os
import re
import time
import json
import time
import json
from typing import Dict, Iterable, List, Optional, Any, Tuple
from decouple import config

from .prompt_service import build_qa_prompt, build_cleaning_prompt, build_structure_prompt, build_chunking_prompt, build_retrieval_prompt, build_validation_prompt
from .llm_service import LLMService

logger = logging.getLogger(__name__)


class RAGService:
    """High-level Retrieval-Augmented-Generation service.

    This service depends on an external Chroma adapter to fetch relevant
    chunks. The Chroma adapter is intentionally dependency-injected via
    the `retriever` argument (duck-typed), so it can be mocked in tests.
    """

    def __init__(self, retriever, llm: Optional[LLMService] = None, default_top_k: int = 5):
        """Create a RAGService.

        retriever: object with method get_relevant(project_id, query, top_k) -> List[Dict]
                   each dict should contain at least 'text' and optional metadata like 'document_id' and 'score'.
        llm: LLMService instance (optional). If omitted, a default will be created.
        """
        self.retriever = retriever
        self.llm = llm or LLMService()
        self.default_top_k = default_top_k
        try:
            self.max_context_chars = int(config('RAG_MAX_CONTEXT_CHARS', default='2500'))
        except Exception:
            self.max_context_chars = 2500
        try:
            self.answer_max_tokens = int(config('RAG_MAX_TOKENS', default='256'))
        except Exception:
            self.answer_max_tokens = 256

    def answer_question(self, project_id: int, chat_session_id: int, question: str, top_k: Optional[int] = None, instruction: Optional[str] = None, document_id: Optional[int] = None) -> Dict[str, object]:
        """Answer a question using retrieval + LLM.

        Returns a dict with keys:
        - 'answer': generated answer string
        - 'sources': list of metadata for retrieved chunks used for citation
        - 'raw_retrieval': raw items returned by retriever
        """
        top_k = top_k or self.default_top_k
        logger.debug('RAGService.answer_question project=%s top_k=%s document_id=%s', project_id, top_k, document_id)

        # 1) retrieve — filter theo document_id nếu có
        items = self.retriever.get_relevant(
            project_id=project_id,
            query=question,
            top_k=top_k,
            chat_session_id=chat_session_id,
            document_id=document_id,
        )

        # 2) build prompt — truyền cả file_name để LLM biết nguồn gốc chunk
        context_items = []
        for it in items:
            text = it.get('text', '')
            metadata = it.get('metadata', {})
            file_name = metadata.get('file_name', '')
            context_items.append({'text': text, 'file_name': file_name})

        # --- RETRIEVAL AGENT (RE-RANKING) ---
        enable_retrieval_agent = config('ENABLE_RETRIEVAL_AGENT', default='True').lower() in ['true', '1', 'yes']
        if enable_retrieval_agent and context_items:
            logger.info(f'[RAGService.retrieval] Kích hoạt Retrieval Agent để đánh giá {len(context_items)} chunks.')
            reranked_items = self.evaluate_and_rerank_chunks(question, context_items)
            if reranked_items:
                context_items = reranked_items
            else:
                logger.warning('[RAGService.retrieval] Retrieval Agent không trả về kết quả hợp lệ, dùng chunks gốc.')

        # --- VALIDATION AGENT ---
        enable_validation = config('ENABLE_VALIDATION_AGENT', default='True').lower() in ['true', '1', 'yes']
        if enable_validation and context_items:
            logger.info('[RAGService.retrieval] Kích hoạt Validation Agent để kiểm tra ngữ cảnh trước khi QA.')
            valid_items = []
            for item in context_items:
                val_res = self.validate_extracted_data(item.get('text', ''))
                if val_res.get('confidence') == 'low':
                    logger.warning(f"[RAGService.retrieval] Validation Agent phát hiện lỗi ở chunk: {val_res.get('issues')}")
                    if val_res.get('corrected_data'):
                        item['text'] = str(val_res.get('corrected_data'))
                        valid_items.append(item)
                else:
                    valid_items.append(item)
            
            if valid_items:
                context_items = valid_items

        prompt = build_qa_prompt(
            question=question,
            contexts=context_items,
            instruction=instruction,
            max_context_chars=self.max_context_chars,
        )

        # 3) call LLM
        answer = self.llm.generate(prompt, max_tokens=self.answer_max_tokens)

        # 4) prepare sources for citation (document_id and chunk index if present)
        sources = []
        for it in items:
            metadata = it.get('metadata', {})\
            
            meta = {
                'document_id': metadata.get('document_id'),
                'chunk_id': it.get('id'),
                'score': it.get('score'),
            }
            sources.append(meta)

        return {
            'answer': answer,
            'sources': sources,
            'raw_retrieval': items,
        }

    def summarize_document(self, document_text: str, file_name: str = '', instruction: Optional[str] = None) -> str:
        """Tóm tắt toàn bộ nội dung một tài liệu."""
        if not document_text or not document_text.strip():
            return 'Tài liệu không có nội dung.'

        # Sử dụng instruction chung của QA & Summary Agent nếu không có
        if not instruction:
            from .prompt_service import get_default_instruction
            instruction = get_default_instruction()

        section_size = self.max_context_chars  # ký tự/section
        # Không truyền tên file lên đầu prompt để tránh LLM bị "ảo giác" (hallucinate) do tiêu đề file
        
        if len(document_text) <= section_size:
            prompt = (
                f"{instruction}\n\n"
                f"VĂN BẢN CẦN TÓM TẮT:\n"
                f"{document_text}\n\n"
                f"Lưu ý quan trọng: KHÔNG giải thích về tên file. Chỉ tóm tắt nội dung thực tế của văn bản trên thành các điểm chính."
            )
            logger.debug('RAGService.summarize_document direct mode, len=%s', len(document_text))
            return self.llm.generate(prompt, max_tokens=self.answer_max_tokens)

        # Map-Reduce: text dài → tóm tắt từng phần theo cấu trúc hành chính → tổng hợp
        logger.debug('RAGService.summarize_document map-reduce mode, total_len=%s', len(document_text))
        try:
            from apps.documents.parser import chunk_administrative_text

            admin_chunks = chunk_administrative_text(document_text, chunk_size=section_size)
            sections = [
                {
                    'text': item.get('chunk', ''),
                    'chunk_type': item.get('chunk_type', 'Khác'),
                }
                for item in admin_chunks
                if item.get('chunk', '').strip()
            ]
        except Exception as exc:
            logger.warning('RAGService.summarize_document administrative chunking failed: %s', exc)
            sections = []

        if not sections:
            sections = [
                {
                    'text': document_text[i:i + section_size],
                    'chunk_type': 'Khác',
                }
                for i in range(0, len(document_text), section_size)
            ]

        section_summaries = []
        for idx, section in enumerate(sections):
            section_text = section.get('text', '')
            chunk_type = section.get('chunk_type', 'Khác')
            section_prompt = (
                f"{instruction}\n\n"
                f"Tóm tắt ngắn gọn phần {idx + 1}/{len(sections)} của văn bản sau.\n"
                f"Loại phần: {chunk_type}.\n"
                f"Chỉ dùng thông tin trong phần này, không tự suy diễn, giữ đúng số hiệu/ngày/tên riêng nếu có:\n\n"
                f"{section_text}"
            )
            summary = self.llm.generate(section_prompt, max_tokens=512)
            section_summaries.append(f"[Phần {idx + 1} - {chunk_type}] {summary}")
            logger.debug('RAGService.summarize_document section %s/%s done', idx + 1, len(sections))

        # Reduce: tổng hợp các bản tóm tắt
        combined = '\n\n'.join(section_summaries)
        reduce_prompt = (
            f"{instruction}\n\n"
            f"Dưới đây là tóm tắt từng phần của một tài liệu. "
            f"Hãy tổng hợp thành một bản tóm tắt hoàn chỉnh, mạch lạc bằng tiếng Việt.\n"
            f"CHỈ DÙNG thông tin dưới đây, KHÔNG bịa thêm:\n\n"
            f"{combined}"
        )
        return self.llm.generate(reduce_prompt, max_tokens=self.answer_max_tokens)

    def clean_document_text(self, text: str, section_size: int = 3000) -> str:
        """Sử dụng LLM để làm sạch text theo tiêu chuẩn Document Cleaning Agent.
        
        Để tránh vượt quá context limit của LLM (gemma3/qwen), tài liệu dài 
        sẽ được chia thành các đoạn nhỏ (section_size) để làm sạch từng đoạn,
        sau đó ghép lại.
        """
        if not text or not text.strip():
            return ""
            
        logger.info(f'[RAGService.clean] Bắt đầu dọn dẹp tài liệu dài {len(text)} ký tự')
        
        # Chia nhỏ để clean
        sections = []
        for i in range(0, len(text), section_size):
            sections.append(text[i:i + section_size])
            
        cleaned_sections = []
        for idx, section in enumerate(sections):
            logger.info(f'[RAGService.clean] Đang xử lý đoạn {idx + 1}/{len(sections)}...')
            prompt = build_cleaning_prompt(section)
            try:
                # Dùng generate() không stream, max_tokens lớn một chút để đảm bảo đủ trả về
                # Nhiệt độ (temperature=0.0) để đảm bảo không bịa thêm chữ
                cleaned = self.llm.generate(prompt, max_tokens=1500, temperature=0.0)
                # Loại bỏ những câu reply dư thừa nếu LLM có thói quen chào hỏi
                cleaned = re.sub(r'^(Dưới đây là|Văn bản sau|Phần text).*?:?\n+', '', cleaned, flags=re.IGNORECASE)
                cleaned_sections.append(cleaned.strip())
            except Exception as e:
                logger.error(f'[RAGService.clean] Lỗi khi xử lý đoạn {idx + 1}: {e}')
                # Nếu LLM fail, giữ nguyên text cũ để không mất dữ liệu
                cleaned_sections.append(section)
                
        final_clean_text = '\n\n'.join(cleaned_sections)
        logger.info(f'[RAGService.clean] Hoàn tất dọn dẹp. Ký tự còn lại: {len(final_clean_text)}')
        return final_clean_text

    def detect_document_structure(self, chunk_text: str) -> Dict[str, Any]:
        """Sử dụng LLM để nhận diện cấu trúc văn bản hành chính theo dạng JSON."""
        if not chunk_text or not chunk_text.strip():
            return {}
            
        logger.info(f'[RAGService.structure] Bắt đầu nhận diện cấu trúc cho đoạn {len(chunk_text)} ký tự')
        prompt = build_structure_prompt(chunk_text)
        
        try:
            # LLM response
            result = self.llm.generate(prompt, max_tokens=1000, temperature=0.0)
            
            # Trích xuất JSON từ kết quả (phòng khi LLM sinh thêm text như ```json ... ```)
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                # Thay thế null/None thành giá trị None hợp lệ trong Python
                parsed_json = json.loads(json_str)
                
                # --- VALIDATION AGENT ---
                enable_validation = config('ENABLE_VALIDATION_AGENT', default='True').lower() in ['true', '1', 'yes']
                if enable_validation:
                    logger.info(f'[RAGService.structure] Chạy Validation Agent để kiểm tra độ chính xác của metadata...')
                    data_to_validate = f"Đoạn văn bản gốc:\n{chunk_text}\n\nMetadata LLM đã trích xuất:\n{json.dumps(parsed_json, ensure_ascii=False, indent=2)}"
                    validation_result = self.validate_extracted_data(data_to_validate)
                    
                    if validation_result.get('confidence') == 'low':
                        logger.warning(f"[RAGService.validation] Phát hiện rủi ro sai sót: {validation_result.get('issues', [])}")
                        corrected = validation_result.get('corrected_data')
                        if corrected and isinstance(corrected, dict):
                            # Ghi đè bằng dữ liệu đã được Validation Agent sửa
                            parsed_json.update(corrected)
                            logger.info("[RAGService.validation] Đã sửa lỗi bằng dữ liệu của Validation Agent.")
                        else:
                            # Nếu không có corrected data rõ ràng, xoá các trường đáng ngờ
                            if 'Cổng thông tin' in str(parsed_json.get('signer', '')).title():
                                parsed_json['signer'] = None
                                
                return parsed_json
            else:
                logger.warning(f'[RAGService.structure] Không tìm thấy JSON hợp lệ trong response: {result[:100]}...')
                return {}
        except Exception as e:
            logger.error(f'[RAGService.structure] Lỗi nhận diện cấu trúc: {e}')
            return {}

    def validate_extracted_data(self, data_str: str) -> Dict[str, Any]:
        """Sử dụng LLM để kiểm tra chéo độ chính xác của metadata/text."""
        prompt = build_validation_prompt(data_str)
        try:
            result = self.llm.generate(prompt, max_tokens=1000, temperature=0.0)
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            return {}
        except Exception as e:
            logger.error(f'[RAGService.validation] Lỗi Validation Agent: {e}')
            return {}

    def intelligent_chunk_document(self, text: str, block_size: int = 2500) -> List[Dict[str, Any]]:
        """Sử dụng LLM để chia nhỏ văn bản thành các chunk theo đúng ngữ nghĩa hành chính.
        
        Trả về danh sách các dict, mỗi dict chứa:
        - chunk: văn bản gốc
        - chunk_type: loại (Điều/Khoản/...)
        - context_score: high/medium/low
        """
        if not text or not text.strip():
            return []
            
        logger.info(f'[RAGService.chunking] Bắt đầu intelligent chunking văn bản {len(text)} ký tự')
        
        # Chia text thành các block vừa phải để tránh giới hạn output tokens của LLM
        blocks = []
        for i in range(0, len(text), block_size):
            blocks.append(text[i:i + block_size])
            
        all_intelligent_chunks = []
        
        for idx, block in enumerate(blocks):
            logger.info(f'[RAGService.chunking] Xử lý block {idx + 1}/{len(blocks)}...')
            prompt = build_chunking_prompt(block)
            
            try:
                result = self.llm.generate(prompt, max_tokens=2500, temperature=0.0)
                
                # Trích xuất mảng JSON từ kết quả
                json_match = re.search(r'\[.*\]', result, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    parsed_array = json.loads(json_str)
                    
                    if isinstance(parsed_array, list):
                        all_intelligent_chunks.extend(parsed_array)
                    else:
                        logger.warning(f'[RAGService.chunking] Result không phải là mảng JSON ở block {idx+1}')
                else:
                    logger.warning(f'[RAGService.chunking] Không tìm thấy mảng JSON hợp lệ ở block {idx+1}')
                    # Fallback: Trả lại text thô
                    all_intelligent_chunks.append({
                        "chunk": block,
                        "chunk_type": "Khác",
                        "context_score": "low"
                    })
                    
            except Exception as e:
                logger.error(f'[RAGService.chunking] Lỗi khi chia block {idx + 1}: {e}')
                all_intelligent_chunks.append({
                    "chunk": block,
                    "chunk_type": "Lỗi",
                    "context_score": "low"
                })
                
        logger.info(f'[RAGService.chunking] Hoàn tất intelligent chunking. Thu được {len(all_intelligent_chunks)} chunks.')
        return all_intelligent_chunks

    def evaluate_and_rerank_chunks(self, question: str, context_items: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Sử dụng LLM để đánh giá (re-rank) lại các chunk trả về từ vector search."""
        if not context_items:
            return []

        # Gộp tất cả chunk thành một khối text để LLM chấm điểm
        # Đánh dấu thứ tự để dễ xử lý (tuy nhiên Agent trả về JSON nên mảng JSON là tốt nhất)
        combined_text = ""
        for idx, item in enumerate(context_items):
            combined_text += f"--- Chunk {idx + 1} (Nguồn: {item.get('file_name', 'Unknown')}) ---\n{item.get('text', '')}\n\n"

        prompt = build_retrieval_prompt(question, combined_text)
        
        try:
            result = self.llm.generate(prompt, max_tokens=2048, temperature=0.0)
            
            # Trích xuất mảng JSON từ kết quả
            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                parsed_array = json.loads(json_str)
                
                if isinstance(parsed_array, list):
                    scored_chunks = []
                    for item in parsed_array:
                        # Chuẩn hoá điểm số
                        try:
                            score = float(item.get('score', 0))
                        except (ValueError, TypeError):
                            score = 0
                        
                        # Chỉ lấy các chunk có điểm tương đối (ví dụ >= 40)
                        if score >= 40:
                            scored_chunks.append({
                                'text': str(item.get('chunk', '')),
                                'file_name': 'Agent Reranked',
                                'score': score,
                                'reason': str(item.get('reason', ''))
                            })
                    
                    # Sắp xếp theo score giảm dần
                    scored_chunks.sort(key=lambda x: x['score'], reverse=True)
                    
                    logger.info(f'[RAGService.retrieval] Đã lọc được {len(scored_chunks)}/{len(context_items)} chunks tốt.')
                    return scored_chunks
            
            logger.warning('[RAGService.retrieval] LLM không trả về mảng JSON hợp lệ cho đánh giá chunk.')
            return []
        except Exception as e:
            logger.error(f'[RAGService.retrieval] Lỗi khi đánh giá chunks: {e}')
            return []

__all__ = ['RAGService']

