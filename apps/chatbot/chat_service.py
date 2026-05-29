"""Chat service - orchestrate chat logic chuẩn production."""
import logging
import os
import re
import time
import unicodedata
from typing import Dict, Optional
from decouple import config

import requests
from django.utils import timezone

from .models import ChatSession, ChatMessage, MessageContext
from .chroma_service import ChromaService
from .rag_service import RAGService
from .prompt_service import get_default_instruction
from apps.documents.models import Document
from apps.realtime.events import send_to_admins

logger = logging.getLogger(__name__)


def _fold_intent_text(text: str) -> str:
	text = unicodedata.normalize('NFD', text or '').lower()
	text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
	return text.replace('đ', 'd').strip()


class ChatService:
	"""Tất cả logic chat đều ở đây - dễ test, dễ maintain."""
	
	def __init__(self):
		self.chroma = ChromaService()
		self.rag = RAGService(retriever=self.chroma)
		try:
			self.default_top_k = int(config('RAG_TOP_K', default='3'))
		except Exception:
			self.default_top_k = 3
		self.signer_patterns = [
			r'ai\s+.*k[yý]',
			r'ng[uư]ời\s+k[yý].*ai',
			r'ai\s+l[aà]\s+ng[uư]ời\s+k[yý]',
			r'v[aă]n\s+b[aả]n.*do\s+ai\s+k[yý]',
			r'k[yý]\s+t[eê]n.*l[aà]\s+ai',
			r'who\s+signed',
			r'signer',
		]
		self.document_number_patterns = [
			r's[oố]\s+v[aă]n\s+b[aả]n',
			r's[oố]\s+c[uủ]a\s+v[aă]n\s+b[aả]n',
			r'v[aă]n\s+b[aả]n\s+s[oố]',
			r'document\s+number',
		]
		self.place_date_patterns = [
			r'ng[aà]y\s+ban\s+h[aà]nh',
			r'ng[aà]y\s+k[yý]',
			r'ban\s+h[aà]nh\s+ng[aà]y',
			r'v[aă]n\s+b[aả]n.*ng[aà]y\s+n[aà]o',
			r'document\s+date',
		]
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
		# Intent patterns để phát hiện yêu cầu tóm tắt
		self.summary_patterns = [
			r'tóm\s+tắt',
			r'tóm\s+lược',
			r'nội\s+dung\s+(chính|chủ\s+yếu|tổng\s+quan)',
			r'(cho|hãy|giúp)\s+(tôi\s+)?(xem|biết)\s+(nội\s+dung|tóm)',
			r'summarize',
			r'summary',
			r'overview',
			r'tổng\s+quan',
			r'điểm\s+chính',
			r'ý\s+chính',
		]

	def _is_small_talk(self, question: str) -> bool:
		if not question:
			return False
		q = _fold_intent_text(question)
		if q in {'chao', 'hi', 'hello', 'hey', 'cam on', 'thanks', 'thank you'}:
			return True
		for pattern in self.small_talk_patterns:
			if re.match(pattern, q):
				return True
		return False

	def _is_summary_request(self, question: str) -> bool:
		"""Phát hiện câu hỏi yêu cầu tóm tắt tài liệu."""
		if not question:
			return False
		q = _fold_intent_text(question)
		if any(keyword in q for keyword in ['tom tat', 'tom luoc', 'tong quan', 'diem chinh', 'y chinh']):
			return True
		for pattern in self.summary_patterns:
			if re.search(pattern, q):
				return True
		return False

	def _is_signer_request(self, question: str) -> bool:
		if not question:
			return False
		q = _fold_intent_text(question)
		if any(keyword in q for keyword in ['nguoi ky', 'ai ky', 'ky ten', 'signer', 'who signed']):
			return True
		for pattern in self.signer_patterns:
			if re.search(pattern, q):
				return True
		return False

	def _is_document_number_request(self, question: str) -> bool:
		if not question:
			return False
		q = _fold_intent_text(question)
		if any(keyword in q for keyword in ['so van ban', 'van ban so', 'document number']):
			return True
		for pattern in self.document_number_patterns:
			if re.search(pattern, q):
				return True
		return False

	def _is_place_date_request(self, question: str) -> bool:
		if not question:
			return False
		q = _fold_intent_text(question)
		if any(keyword in q for keyword in ['ngay ban hanh', 'ngay ky', 'ban hanh ngay', 'document date']):
			return True
		for pattern in self.place_date_patterns:
			if re.search(pattern, q):
				return True
		return False

	def _detect_intent(self, question: str) -> str:
		"""Phân loại intent câu hỏi.

		Returns:
			'small_talk' | 'summary' | 'qa'
		"""
		if self._is_small_talk(question):
			return 'small_talk'
		if self._is_signer_request(question):
			return 'signer'
		if self._is_document_number_request(question):
			return 'document_number'
		if self._is_place_date_request(question):
			return 'place_date'
		if self._is_summary_request(question):
			return 'summary'
		return 'qa'

	def _answer_small_talk(self, question: str) -> str:
		prompt = (
			"Bạn là trợ lý thân thiện. Trả lời tự nhiên, ngắn gọn, lịch sự bằng tiếng Việt "
			"cho câu xã giao sau, không cần trích dẫn nguồn:\n\n"
			f"Câu người dùng: {question}"
		)
		return self.rag.llm.generate(prompt, max_tokens=120, temperature=0.4)

	def _handle_summary(self, session, question: str, document_id: Optional[int] = None) -> tuple:
		"""Xử lý yêu cầu tóm tắt — dùng extracted_text thay vì RAG chunking.

		Returns:
			(answer_text, retrieved_chunks)
		"""
		from apps.teams.permissions import accessible_documents_for_session
		documents = list(accessible_documents_for_session(session).order_by('uploaded_at'))
		if not documents:
			return 'Chưa có tài liệu nào trong cuộc trò chuyện này.', []

		# Nếu có document_id cụ thể → tóm tắt file đó
		if document_id:
			target_docs = [d for d in documents if d.id == document_id]
			if not target_docs:
				return f'Không tìm thấy tài liệu #{document_id} trong cuộc trò chuyện này.', []
		else:
			# Không chỉ định → tóm tắt tất cả (mỗi file 1 bản)
			target_docs = documents

		summaries = []
		for doc in target_docs:
			if not doc.extracted_text or not doc.extracted_text.strip():
				summaries.append(f'**{doc.title}**: Chưa có nội dung được trích xuất.')
				continue
			logger.info('[ChatService] Summarizing document id=%s title=%s len=%s', doc.id, doc.title, len(doc.extracted_text))
			summary = self.rag.summarize_document(
				document_text=doc.extracted_text,
				file_name=doc.title,
			)
			summaries.append(f'**{doc.title}**:\n{summary}')

		answer_text = '\n\n---\n\n'.join(summaries)
		return answer_text, []

	def _handle_signer_question(self, session, document_id: Optional[int] = None) -> tuple:
		"""Answer signer questions from extracted fields only."""
		from apps.teams.permissions import accessible_documents_for_session
		documents = list(accessible_documents_for_session(session).order_by('uploaded_at'))
		if not documents:
			return 'Chưa có tài liệu nào trong cuộc trò chuyện này.', []

		if document_id:
			target_docs = [doc for doc in documents if doc.id == document_id]
			if not target_docs:
				return f'Không tìm thấy tài liệu #{document_id} trong cuộc trò chuyện này.', []
		else:
			target_docs = documents

		from apps.documents.field_validators import is_valid_signer_field

		answers = []
		for doc in target_docs:
			fields = doc.extracted_fields or {}
			signer = fields.get('signer') or {}
			if not is_valid_signer_field(signer):
				answers.append(f'**{doc.title}**: Không xác định được người ký từ vùng chữ ký của tài liệu.')
				continue

			evidence = signer.get('evidence') or []
			evidence_text = '\n'.join(f'- {line}' for line in evidence)
			answers.append(
				f"**{doc.title}**: Người ký là {signer.get('value')}.\n\n"
				f"Bằng chứng:\n{evidence_text}"
			)

		return '\n\n---\n\n'.join(answers), []

	def _handle_extracted_field_question(self, session, field_key: str, label: str, document_id: Optional[int] = None) -> tuple:
		"""Answer deterministic document-field questions from extracted fields."""
		from apps.teams.permissions import accessible_documents_for_session
		documents = list(accessible_documents_for_session(session).order_by('uploaded_at'))
		if not documents:
			return 'Chưa có tài liệu nào trong cuộc trò chuyện này.', []

		if document_id:
			target_docs = [doc for doc in documents if doc.id == document_id]
			if not target_docs:
				return f'Không tìm thấy tài liệu #{document_id} trong cuộc trò chuyện này.', []
		else:
			target_docs = documents

		from apps.documents.field_validators import is_valid_extracted_field

		answers = []
		for doc in target_docs:
			field = (doc.extracted_fields or {}).get(field_key) or {}
			if not is_valid_extracted_field(field):
				answers.append(f'**{doc.title}**: Không xác định được {label.lower()} từ tài liệu.')
				continue

			evidence = field.get('evidence')
			answer = f"**{doc.title}**: {label} là {field.get('value')}."
			if evidence:
				answer += f"\n\nBằng chứng:\n- {evidence}"
			answers.append(answer)

		return '\n\n---\n\n'.join(answers), []
	
	def create_session(self, project_id: int, title: Optional[str] = None, user=None) -> ChatSession:
		"""Tạo session chat mới.
		
		Args:
			project_id: ID project
			title: optional title (sẽ tự sinh từ câu hỏi đầu tiên nếu không có)
		
		Returns:
			ChatSession instance
		"""
		logger.info(f'[ChatService] Creating session for project_id={project_id}')
		
		if not user:
			raise ValueError('User is required to create a chat session')

		session = ChatSession.objects.create(
			project_id=project_id,
			user=user,
			title=title or 'Chat mới'
		)
		
		logger.info(f'[ChatService] Session created: id={session.id}')
		return session
	
	def ask_question(self, session_id: int, question: str, document_id: Optional[int] = None) -> Dict:
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
		documents = list(session.documents.filter(is_deleted=False).order_by('uploaded_at'))
		logger.info('[ChatService] document_id from request: %s', document_id)
		logger.info(
			'[ChatService] session=%s project=%s documents=%s',
			session_id,
			project_id,
			[d.id for d in documents],
		)
		
		# [2] Lưu user message ngay
		user_msg = ChatMessage.objects.create(
			chat_session=session,
			role=ChatMessage.Role.USER,
			content=question
		)
		send_to_admins('dashboard.query.created', {
			'message_id': user_msg.id,
			'chat_session_id': session.id,
			'project_id': project_id,
			'user_id': session.user_id,
			'created_at': user_msg.created_at.isoformat(),
		})
		logger.info(f'[ChatService] User message saved: id={user_msg.id}')
		
		# [3] Intent routing + generation
		try:
			started_at = time.perf_counter()
			intent = self._detect_intent(question)
			logger.info('[ChatService] Intent detected: %s', intent)

			if intent == 'small_talk':
				logger.info('[ChatService] Small-talk mode, bypassing retrieval')
				answer_text = self._answer_small_talk(question)
				retrieved_chunks = []

			elif intent == 'summary':
				logger.info('[ChatService] Summary mode, using extracted_text (document_id=%s)', document_id)
				answer_text, retrieved_chunks = self._handle_summary(session, question, document_id=document_id)

			elif intent == 'signer':
				logger.info('[ChatService] Signer mode, using extracted_fields (document_id=%s)', document_id)
				answer_text, retrieved_chunks = self._handle_signer_question(session, document_id=document_id)

			elif intent == 'document_number':
				logger.info('[ChatService] Document number mode, using extracted_fields (document_id=%s)', document_id)
				answer_text, retrieved_chunks = self._handle_extracted_field_question(
					session,
					field_key='document_number',
					label='Số văn bản',
					document_id=document_id,
				)

			elif intent == 'place_date':
				logger.info('[ChatService] Place/date mode, using extracted_fields (document_id=%s)', document_id)
				answer_text, retrieved_chunks = self._handle_extracted_field_question(
					session,
					field_key='place_date',
					label='Ngày ban hành',
					document_id=document_id,
				)

			else:  # qa
				logger.info('[ChatService] QA mode (grounded), document_id=%s', document_id)
				result = self.rag.answer_question(
					project_id=project_id,
					chat_session_id=session.id,
					question=question,
					top_k=self.default_top_k,
					instruction=get_default_instruction(),
					document_id=document_id,
				)
				answer_text = result.get('answer', '')
				retrieved_chunks = result.get('raw_retrieval', [])

				# Guardrail: câu hỏi QA phải có ít nhất 1 chunk liên quan
				if not retrieved_chunks:
					answer_text = 'Không có thông tin trong tài liệu đã chọn để trả lời câu hỏi này.'

			logger.info(f'[ChatService] Generation completed, answer_len={len(answer_text)}, chunks={len(retrieved_chunks)}, elapsed={time.perf_counter() - started_at:.2f}s')
			
		except Exception as exc:
			logger.error(f'[ChatService] RAG failed: {exc}', exc_info=True)
			# Lưu error message vẫn có để user thấy
			if isinstance(exc, requests.exceptions.ReadTimeout) or 'Read timed out' in str(exc):
				answer_text = 'Hệ thống đang xử lý lâu hơn dự kiến. Vui lòng thử lại hoặc rút gọn câu hỏi.'
			else:
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
			for doc in Document.objects.filter(id__in=doc_ids, is_deleted=False)
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

	def ask_question_stream(self, session_id: int, question: str, document_id: Optional[int] = None):
		"""Streaming version của ask_question — generator cho SSE.

		Yield các SSE event:
		  data: {"type": "token", "content": "..."}    ← từng token LLM sinh ra
		  data: {"type": "done", "message_id": 123}    ← khi hoàn tất, kèm message_id để FE sync
		  data: {"type": "error", "content": "..."}    ← nếu có lỗi

		Flow:
		1. Validate session
		2. Lưu user message
		3. Retrieval (ChromaDB)
		4. Build prompt
		5. Stream LLM tokens → yield từng SSE event
		6. Sau khi stream xong, lưu assistant message vào DB
		7. Yield event done
		"""
		import json as _json

		logger.info('[ChatService.stream] session_id=%s question=%s document_id=%s', session_id, question[:50], document_id)

		# [1] Validate session
		try:
			session = ChatSession.objects.get(id=session_id)
		except ChatSession.DoesNotExist:
			yield f'data: {_json.dumps({"type": "error", "content": f"Session {session_id} không tồn tại"})}\n\n'
			return

		project_id = session.project_id

		# [2] Lưu user message ngay
		user_msg = ChatMessage.objects.create(
			chat_session=session,
			role=ChatMessage.Role.USER,
			content=question,
		)
		send_to_admins('dashboard.query.created', {
			'message_id': user_msg.id,
			'chat_session_id': session.id,
			'project_id': project_id,
			'user_id': session.user_id,
			'created_at': user_msg.created_at.isoformat(),
		})
		logger.info('[ChatService.stream] User message saved: id=%s', user_msg.id)

		# Yield event báo user message đã lưu (FE có thể hiện message ngay)
		yield f'data: {_json.dumps({"type": "user_saved", "message_id": user_msg.id})}\n\n'

		# [3] Intent detection
		intent = self._detect_intent(question)
		logger.info('[ChatService.stream] Intent: %s', intent)

		answer_text = ''
		retrieved_chunks = []

		if intent == 'small_talk':
			answer_text = 'Chào bạn. Bạn muốn hỏi gì về tài liệu?'
			yield f'data: {_json.dumps({"type": "token", "content": answer_text})}\n\n'

		elif intent == 'summary':
			# Summary: không stream được tốt (Map-Reduce nhiều bước)
			# → dùng generate() bình thường nhưng yield result cuối
			yield f'data: {_json.dumps({"type": "token", "content": "Đang tóm tắt tài liệu..."})}\n\n'
			answer_text, retrieved_chunks = self._handle_summary(session, question, document_id=document_id)
			# Yield toàn bộ text summary dưới dạng 1 token lớn
			yield f'data: {_json.dumps({"type": "token", "content": answer_text})}\n\n'

		elif intent == 'signer':
			answer_text, retrieved_chunks = self._handle_signer_question(session, document_id=document_id)
			yield f'data: {_json.dumps({"type": "token", "content": answer_text})}\n\n'

		elif intent == 'document_number':
			answer_text, retrieved_chunks = self._handle_extracted_field_question(
				session,
				field_key='document_number',
				label='Số văn bản',
				document_id=document_id,
			)
			yield f'data: {_json.dumps({"type": "token", "content": answer_text})}\n\n'

		elif intent == 'place_date':
			answer_text, retrieved_chunks = self._handle_extracted_field_question(
				session,
				field_key='place_date',
				label='Ngày ban hành',
				document_id=document_id,
			)
			yield f'data: {_json.dumps({"type": "token", "content": answer_text})}\n\n'

		else:  # qa — streaming RAG
			# [3a] Retrieval từ ChromaDB
			try:
				items = self.chroma.get_relevant(
					project_id=project_id,
					query=question,
					top_k=self.default_top_k,
					chat_session_id=session.id,
					document_id=document_id,
				)
				retrieved_chunks = items
			except Exception as exc:
				logger.error('[ChatService.stream] Retrieval failed: %s', exc)
				items = []
				retrieved_chunks = []

			if not retrieved_chunks:
				no_info = 'Không có thông tin trong tài liệu đã chọn để trả lời câu hỏi này.'
				answer_text = no_info
				yield f'data: {_json.dumps({"type": "token", "content": no_info})}\n\n'
			else:
				# [3b] Build prompt
				from .prompt_service import build_qa_prompt
				context_items = [
					{'text': it.get('text', ''), 'file_name': it.get('metadata', {}).get('file_name', '')}
					for it in items
				]

				# --- RETRIEVAL AGENT (RE-RANKING) ---
				enable_retrieval_agent = config('ENABLE_RETRIEVAL_AGENT', default='True').lower() in ['true', '1', 'yes']
				if enable_retrieval_agent and context_items:
					logger.info(f'[ChatService.stream] Kích hoạt Retrieval Agent để đánh giá {len(context_items)} chunks.')
					reranked_items = self.rag.evaluate_and_rerank_chunks(question, context_items)
					if reranked_items:
						context_items = reranked_items
					else:
						logger.warning('[ChatService.stream] Retrieval Agent không trả về kết quả hợp lệ, dùng chunks gốc.')

				# --- VALIDATION AGENT ---
				enable_validation = config('ENABLE_VALIDATION_AGENT', default='True').lower() in ['true', '1', 'yes']
				if enable_validation and context_items:
					logger.info('[ChatService.stream] Kích hoạt Validation Agent để kiểm tra ngữ cảnh trước khi QA.')
					valid_items = []
					for item in context_items:
						val_res = self.rag.validate_extracted_data(item.get('text', ''))
						if val_res.get('confidence') == 'low':
							logger.warning(f"[ChatService.stream] Validation Agent phát hiện lỗi ở chunk: {val_res.get('issues')}")
							# Có thể dùng corrected_data nếu có, hoặc giữ nguyên nhưng cảnh báo
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
					instruction=get_default_instruction(),
					max_context_chars=self.rag.max_context_chars,
				)

				# [3c] Stream LLM tokens
				logger.info('[ChatService.stream] Starting LLM stream, prompt_len=%d, max_tokens=%d', len(prompt), self.rag.answer_max_tokens)
				try:
					stream_token_count = 0
					for token in self.rag.llm.generate_stream(prompt, max_tokens=self.rag.answer_max_tokens):
						stream_token_count += 1
						answer_text += token
						yield f'data: {_json.dumps({"type": "token", "content": token})}\n\n'
					logger.info('[ChatService.stream] LLM stream done: tokens=%d answer_len=%d', stream_token_count, len(answer_text))
					if not answer_text.strip():
						answer_text = 'Không tạo được phản hồi từ mô hình. Vui lòng thử lại hoặc kiểm tra cấu hình Ollama.'
						yield f'data: {_json.dumps({"type": "token", "content": answer_text})}\n\n'
				except Exception as llm_exc:
					logger.error('[ChatService.stream] LLM stream exception: %s', llm_exc, exc_info=True)
					error_msg = f'[Lỗi LLM: {str(llm_exc)[:80]}]'
					answer_text = error_msg
					yield f'data: {_json.dumps({"type": "token", "content": error_msg})}\n\n'

		# [4] Lưu assistant message sau khi stream xong
		try:
			# Build sources từ retrieved_chunks
			contexts_payload = []
			if retrieved_chunks:
				doc_ids = {
					chunk.get('metadata', {}).get('document_id')
					for chunk in retrieved_chunks
					if chunk.get('metadata', {}).get('document_id')
				}
				docs_map = {
					doc.id: doc
					for doc in Document.objects.filter(id__in=doc_ids, is_deleted=False)
				}
				context_objects = []
				for chunk in retrieved_chunks:
					metadata = chunk.get('metadata', {})
					doc_id = metadata.get('document_id')
					doc = docs_map.get(doc_id)
					if not doc:
						continue
					chunk_id = str(chunk.get('id') or f"{doc_id}_{metadata.get('chunk_index', 0)}")
					context_objects.append(MessageContext(
						message=user_msg,
						document=doc,
						chunk_id=chunk_id,
						score=chunk.get('score'),
						content_preview=(chunk.get('text') or '')[:500],
					))
				if context_objects:
					MessageContext.objects.bulk_create(context_objects)
					for item in context_objects:
						contexts_payload.append({
							'document_id': item.document_id,
							'chunk_id': item.chunk_id,
							'score': item.score,
							'preview': item.content_preview,
						})

			sources = [
				{'document_id': item['document_id'], 'score': item['score'], 'text': item['preview']}
				for item in contexts_payload
			]

			assistant_msg = ChatMessage.objects.create(
				chat_session=session,
				role=ChatMessage.Role.ASSISTANT,
				content=answer_text,
				sources=sources,
				model_name=self.rag.llm.model,
				temperature=0.0,
				tokens_used=0,
				metadata={},
			)
			session.last_message_at = timezone.now()
			session.update_title_from_first_message()
			session.save(update_fields=['updated_at', 'last_message_at'])
			logger.info('[ChatService.stream] Assistant message saved: id=%s len=%s', assistant_msg.id, len(answer_text))

			# [5] Yield done event kèm message_id để FE load message đầy đủ
			yield f'data: {_json.dumps({"type": "done", "message_id": assistant_msg.id, "session_id": session.id})}\n\n'

		except Exception as exc:
			logger.error('[ChatService.stream] Failed to save assistant message: %s', exc, exc_info=True)
			yield f'data: {_json.dumps({"type": "error", "content": "Lỗi lưu tin nhắn: " + str(exc)[:80]})}\n\n'


__all__ = ['ChatService']

