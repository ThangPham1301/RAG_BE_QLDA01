"""Chat service - orchestrate chat logic chuẩn production."""
import logging
import os
import re
from typing import Dict, Optional

from django.utils import timezone

from .models import ChatSession, ChatMessage, MessageContext
from .chroma_service import ChromaService
from .rag_service import RAGService
from .prompt_service import get_default_instruction
from apps.documents.models import Document

logger = logging.getLogger(__name__)


class ChatService:
	"""Tất cả logic chat đều ở đây - dễ test, dễ maintain."""
	
	def __init__(self):
		self.chroma = ChromaService()
		self.rag = RAGService(retriever=self.chroma)
		try:
			self.default_top_k = int(os.environ.get('RAG_TOP_K', '3'))
		except Exception:
			self.default_top_k = 3
		# Hybrid mode: small-talk is answered naturally, business questions must be grounded in sources.
		self.small_talk_patterns = [
			r'^\s*ch[aà]o+\s*$',
			r'^\s*hi+\s*$',
			r'^\s*hello+\s*$',
			r'^\s*hey+\s*$',
			r'^\s*b[aạ]n\s+kho[eẻ]\s+kh[oỏ]e\s+kh[oô]ng\??\s*$',
			r'^\s*how\s+are\s+you\??\s*$',
			r'^\s*good\s+(morning|afternoon|evening)\s*$',
			r'^\s*c[aả]m\s+[oơ]n\s*$',
			r'^\s*thanks\s*$',
		]

	def _is_small_talk(self, question: str) -> bool:
		if not question:
			return False
		q = question.strip().lower()
		for pattern in self.small_talk_patterns:
			if re.match(pattern, q):
				return True
		return False

	def _answer_small_talk(self, question: str) -> str:
		prompt = (
			"Bạn là trợ lý thân thiện. Trả lời tự nhiên, ngắn gọn, lịch sự bằng tiếng Việt "
			"cho câu xã giao sau, không cần trích dẫn nguồn:\n\n"
			f"Câu người dùng: {question}"
		)
		return self.rag.llm.generate(prompt, max_tokens=120, temperature=0.4)
	
	def create_session(self, project_id: int, title: Optional[str] = None) -> ChatSession:
		"""Tạo session chat mới.
		
		Args:
			project_id: ID project
			title: optional title (sẽ tự sinh từ câu hỏi đầu tiên nếu không có)
		
		Returns:
			ChatSession instance
		"""
		logger.info(f'[ChatService] Creating session for project_id={project_id}')
		
		session = ChatSession.objects.create(
			project_id=project_id,
			title=title or 'Chat mới'
		)
		
		logger.info(f'[ChatService] Session created: id={session.id}')
		return session
	
	def ask_question(self, session_id: int, question: str, selected_document_ids: Optional[list[int]] = None) -> Dict:
		"""Hỏi đáp qua chat - orchestrate toàn bộ flow.
		
		Flow:
		1. Validate session tồn tại
		2. Lưu user message ngay (UX: input hiển thị nhanh)
		3. RAG retrieval + LLM generation
		4. Lưu assistant message + sources
		5. Update session metadata
		6. Trả response
		
		Args:
			session_id: ID session
			question: Câu hỏi từ user
		
		Returns:
			{
				"message": {...},
				"answer": "...",
				"contexts": [...]
			}
		"""
		logger.info(f'[ChatService.ask_question] session_id={session_id}, question={question[:50]}')
		
		# [1] Validate session
		try:
			session = ChatSession.objects.get(id=session_id)
		except ChatSession.DoesNotExist:
			raise ValueError(f'Session {session_id} không tồn tại')
		
		project_id = session.project_id
		selected_document_ids = selected_document_ids if selected_document_ids is not None else (session.selected_document_ids or [])
		
		# [2] Lưu user message ngay
		user_msg = ChatMessage.objects.create(
			chat_session=session,
			role=ChatMessage.Role.USER,
			content=question
		)
		logger.info(f'[ChatService] User message saved: id={user_msg.id}')
		
		# [3] RAG generation
		try:
			if self._is_small_talk(question):
				logger.info('[ChatService] Small-talk mode detected, bypassing retrieval')
				answer_text = self._answer_small_talk(question)
				retrieved_chunks = []
			else:
				logger.info('[ChatService] Starting RAG generation (grounded mode)')
				result = self.rag.answer_question(
					project_id=project_id,
					question=question,
					top_k=self.default_top_k,
					instruction=get_default_instruction(),
					document_ids=selected_document_ids,
				)
				
				answer_text = result.get('answer', '')
				retrieved_chunks = result.get('raw_retrieval', [])

				# Hybrid mode guardrail: business questions must be grounded by at least one source chunk.
				if not retrieved_chunks:
					answer_text = 'Không có thông tin trong tài liệu đã chọn để trả lời câu hỏi này.'

			logger.info(f'[ChatService] Generation completed, answer_len={len(answer_text)}')
			
		except Exception as exc:
			logger.error(f'[ChatService] RAG failed: {exc}', exc_info=True)
			# Lưu error message vẫn có để user thấy
			answer_text = f'Có lỗi xảy ra khi xử lý câu hỏi: {str(exc)[:100]}'
			retrieved_chunks = []
		
		# [4] Persist retrieval contexts at message level for traceability.
		contexts_payload = []
		if retrieved_chunks:
			doc_ids = {
				chunk.get('metadata', {}).get('document_id')
				for chunk in retrieved_chunks
				if chunk.get('metadata', {}).get('document_id')
			}
			documents = {
				doc.id: doc
				for doc in Document.objects.filter(id__in=doc_ids, project_id=project_id)
			}

			context_objects = []
			for chunk in retrieved_chunks:
				metadata = chunk.get('metadata', {})
				doc_id = metadata.get('document_id')
				doc = documents.get(doc_id)
				if not doc:
					logger.warning('[ChatService] Skip context: document_id=%s not found in project=%s', doc_id, project_id)
					continue

				chunk_id = str(chunk.get('id') or metadata.get('chunk_id') or f"{doc_id}_{metadata.get('chunk_index', 0)}")
				score = chunk.get('score')
				preview = (chunk.get('text') or '')[:500]
				context_objects.append(
					MessageContext(
						message=user_msg,
						document=doc,
						chunk_id=chunk_id,
						score=score if isinstance(score, (int, float)) else None,
						content_preview=preview,
					)
				)

			if context_objects:
				MessageContext.objects.bulk_create(context_objects)
				for item in context_objects:
					contexts_payload.append(
						{
							'document_id': item.document_id,
							'chunk_id': item.chunk_id,
							'score': item.score,
							'preview': item.content_preview,
						}
					)

		# Keep lightweight sources in assistant for backward-compatible history rendering.
		sources = [
			{
				'document_id': item['document_id'],
				'score': item['score'],
				'text': item['preview'],
			}
			for item in contexts_payload
		]

		# [5] Lưu assistant message
		assistant_msg = ChatMessage.objects.create(
			chat_session=session,
			role=ChatMessage.Role.ASSISTANT,
			content=answer_text,
			sources=sources,
			model_name='qwen3-vl:4b',
			temperature=0.0,
			tokens_used=0,  # TODO: track thực tế
			metadata={}
		)
		logger.info(f'[ChatService] Assistant message saved: id={assistant_msg.id}')
		
		# [6] Update session
		session.last_message_at = timezone.now()
		
		# Auto-generate title từ câu hỏi đầu tiên
		session.update_title_from_first_message()
		
		session.save(update_fields=['updated_at', 'last_message_at'])
		logger.info(f'[ChatService] Session updated: {session.id}')
		
		# [7] Format response
		return {
			'message': {
				'id': assistant_msg.id,
				'role': assistant_msg.role,
				'content': assistant_msg.content,
				'sources': assistant_msg.sources,
				'model_name': assistant_msg.model_name,
				'created_at': assistant_msg.created_at.isoformat()
			},
			'answer': assistant_msg.content,
			'contexts': contexts_payload
		}
	
	def get_session_messages(self, session_id: int, limit: int = 50) -> list:
		"""Lấy lịch sử chat của session.
		
		Args:
			session_id: ID session
			limit: Số messages max (mặc định 50)
		
		Returns:
			List of ChatMessage objects (ordered by created_at)
		"""
		logger.info(f'[ChatService] Getting messages for session_id={session_id}')
		
		try:
			session = ChatSession.objects.get(id=session_id)
		except ChatSession.DoesNotExist:
			raise ValueError(f'Session {session_id} không tồn tại')
		
		# Fetch messages, optionally limit
		messages = session.messages.all().order_by('created_at')
		
		if limit:
			messages = messages[max(0, messages.count() - limit):]  # Get last N
		
		logger.info(f'[ChatService] Returning {messages.count()} messages')
		return list(messages)
	
	def get_session_context(self, session_id: int, max_messages: int = 10) -> list:
		"""Lấy context từ previous messages cho conversation continuity.
		
		Dùng khi muốn pass context lịch sử vào LLM.
		
		Args:
			session_id: ID session
			max_messages: Số messages lấy từ history (mặc định 10)
		
		Returns:
			List of {role, content} dicts
		"""
		logger.info(f'[ChatService] Getting context for session_id={session_id}')
		
		messages = self.get_session_messages(session_id, limit=max_messages)
		
		context = [
			{'role': m.role, 'content': m.content}
			for m in messages
		]
		
		logger.info(f'[ChatService] Context prepared with {len(context)} messages')
		return context


__all__ = ['ChatService']
