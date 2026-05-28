from __future__ import annotations

import logging
from pathlib import Path
from decouple import config

from django.utils import timezone as django_timezone

from apps.chatbot.chroma_service import ChromaService

from .admin_doc_extractor import extract_administrative_fields
from .models import Document
from .ocr_layout_service import OCRLayoutService
from .parser import chunk_administrative_text, extract_text_from_docx, extract_text_from_pdf, extract_text_from_image
from .text_normalizer import layout_to_text, normalize_ocr_text

logger = logging.getLogger(__name__)


def _extract_text_from_txt(path: str) -> str:
	try:
		return Path(path).read_text(encoding='utf-8', errors='ignore')
	except Exception:
		return ''


def populate_document_extracted_text(document: Document) -> int:
	logger.info(f'[populate_document_extracted_text] Starting for doc_id={document.id}')
	
	if not document.file:
		logger.warning(f'[populate_document_extracted_text] No file attached')
		raise ValueError('Document has no file attached')

	# Get file path from Django's FileField
	try:
		file_path = document.file.path
	except Exception as e:
		logger.error(f'[populate_document_extracted_text] Could not get file.path: {e}')
		raise
	
	logger.info(f'[populate_document_extracted_text] File path: {file_path}')
	
	abs_path = Path(file_path)
	if not abs_path.exists():
		logger.error(f'[populate_document_extracted_text] File NOT FOUND at {abs_path}')
		raise FileNotFoundError(f'File not found: {file_path}')

	file_size = abs_path.stat().st_size
	logger.info(f'[populate_document_extracted_text] File exists: {abs_path}, size={file_size} bytes')
	
	file_type = (document.file_type or abs_path.suffix.lstrip('.')).lower()
	logger.info(f'[populate_document_extracted_text] Detected file_type={file_type} (document.file_type={document.file_type})')
	
	try:
		if file_type == Document.FileType.PDF or file_type == 'pdf':
			logger.info(f'[populate_document_extracted_text] Extracting as PDF')
			text = extract_text_from_pdf(str(abs_path))
			logger.info(f'[populate_document_extracted_text] PDF extraction result: {len(text or "")} chars')
		elif file_type == Document.FileType.DOCX or file_type == 'docx':
			logger.info(f'[populate_document_extracted_text] Extracting as DOCX')
			text = extract_text_from_docx(str(abs_path))
			logger.info(f'[populate_document_extracted_text] DOCX extraction result: {len(text or "")} chars')
		elif file_type == Document.FileType.TXT or file_type == 'txt':
			logger.info(f'[populate_document_extracted_text] Extracting as TXT')
			text = _extract_text_from_txt(str(abs_path))
			logger.info(f'[populate_document_extracted_text] TXT extraction result: {len(text or "")} chars')
		elif file_type in ['jpg', 'jpeg', 'png']:
			logger.info(f'[populate_document_extracted_text] Extracting as Image (OCR)')
			text = extract_text_from_image(str(abs_path))
			logger.info(f'[populate_document_extracted_text] Image OCR extraction result: {len(text or "")} chars')
		else:
			logger.warning(f'[populate_document_extracted_text] Unknown file type: {file_type}, returning empty')
			text = ''
			
	except Exception as e:
		logger.error(f'[populate_document_extracted_text] Extraction failed: {e}', exc_info=True)
		raise

	text = normalize_ocr_text(text or '')
	ocr_layout = {}
	if file_type in [Document.FileType.PDF, 'pdf', Document.FileType.IMAGE, 'image', 'jpg', 'jpeg', 'png']:
		try:
			logger.info(f'[populate_document_extracted_text] Extracting OCR layout for doc_id={document.id}')
			ocr_service = OCRLayoutService()
			if file_type == Document.FileType.PDF or file_type == 'pdf':
				ocr_layout = ocr_service.extract_pdf_layout(str(abs_path))
			else:
				ocr_layout = ocr_service.extract_image_layout(str(abs_path))
			logger.info(
				'[populate_document_extracted_text] OCR layout pages=%s',
				len((ocr_layout or {}).get('pages') or []),
			)
		except Exception as layout_exc:
			logger.warning(
				'[populate_document_extracted_text] OCR layout extraction failed: %s',
				layout_exc,
				exc_info=True,
			)
			ocr_layout = {}

	layout_text = layout_to_text(ocr_layout or {})
	if layout_text and len(layout_text) >= int(config('OCR_LAYOUT_TEXT_MIN_CHARS', default=200)):
		logger.info(
			'[populate_document_extracted_text] Using OCR layout text as extracted_text source: %s chars',
			len(layout_text),
		)
		text = layout_text

	extracted_fields = {}
	try:
		extracted_fields = extract_administrative_fields(ocr_layout or {}, plain_text=text)
	except Exception as fields_exc:
		logger.warning(
			'[populate_document_extracted_text] Administrative field extraction failed: %s',
			fields_exc,
			exc_info=True,
		)

	if not text or not text.strip():
		logger.warning(f'[populate_document_extracted_text] Extracted text is empty or whitespace-only')
	else:
		# Bước 2: Làm sạch text qua LLM Document Cleaning Agent (tuỳ chọn)
		enable_cleaning = config('ENABLE_DOC_CLEANING', default='True').lower() in ['true', '1', 'yes']
		if enable_cleaning:
			try:
				logger.info(f'[populate_document_extracted_text] Bắt đầu dọn dẹp text qua LLM...')
				from apps.chatbot.rag_service import RAGService
				rag_svc = RAGService(retriever=None)
				text = normalize_ocr_text(rag_svc.clean_document_text(text))
			except Exception as clean_exc:
				logger.error(f'[populate_document_extracted_text] Lỗi làm sạch text: {clean_exc}', exc_info=True)
				# Vẫn giữ nguyên text cũ nếu bị lỗi
	
	document.extracted_text = text or ''
	document.ocr_layout = ocr_layout or {}
	document.extracted_fields = extracted_fields or {}
	document.save(update_fields=['extracted_text', 'ocr_layout', 'extracted_fields'])
	logger.info(f'[populate_document_extracted_text] Saved extracted_text: {len(document.extracted_text)} chars')
	return len(document.extracted_text)


def index_document_to_chroma(document: Document, chunk_size: int = 1000, overlap: int = 200) -> int:
	logger.info(f'[index_document_to_chroma] Starting for doc_id={document.id}, chat_session_id={document.chat_session_id}, project_id={document.chat_session.project_id}')
	Document.objects.filter(pk=document.pk).update(index_status=Document.IndexStatus.INDEXING, index_error='')
	document.refresh_from_db(fields=['extracted_text', 'file', 'chat_session_id', 'index_status', 'index_error'])

	try:
		text = document.extracted_text or ''
		logger.info(f'[index_document_to_chroma] Initial text len={len(text)}')
		if not text.strip():
			logger.info(f'[index_document_to_chroma] Text empty, re-extracting')
			populate_document_extracted_text(document)
			document.refresh_from_db(fields=['extracted_text'])
			text = document.extracted_text or ''
			logger.info(f'[index_document_to_chroma] After re-extract, text len={len(text)}')

		if not text.strip():
			logger.warning(f'[index_document_to_chroma] Still no text after extract')
			Document.objects.filter(pk=document.pk).update(
				index_status=Document.IndexStatus.FAILED,
				index_error='Không trích xuất được nội dung từ file.',
				indexed_chunks=0,
			)
			return 0

		enable_intelligent_chunking = config('ENABLE_INTELLIGENT_CHUNKING', default='True').lower() in ['true', '1', 'yes']
		
		# Khởi tạo RAGService và cờ cấu trúc
		from apps.chatbot.rag_service import RAGService
		rag_svc = RAGService(retriever=None)
		
		if enable_intelligent_chunking:
			logger.info(f'[index_document_to_chroma] Calling intelligent_chunk_document')
			intelligent_chunks = rag_svc.intelligent_chunk_document(text)
			logger.info(f'[index_document_to_chroma] Intelligent chunks created: {len(intelligent_chunks)}')
			
			if not intelligent_chunks:
				logger.warning(f'[index_document_to_chroma] No intelligent chunks created')
				Document.objects.filter(pk=document.pk).update(
					index_status=Document.IndexStatus.FAILED,
					index_error='Không tạo được chunk nào qua AI.',
					indexed_chunks=0,
				)
				return 0
		else:
			logger.info(f'[index_document_to_chroma] Calling rule-based administrative chunking with chunk_size={chunk_size}')
			intelligent_chunks = chunk_administrative_text(text=text, chunk_size=chunk_size)
			logger.info(f'[index_document_to_chroma] Rule-based chunks created: {len(intelligent_chunks)}')
			
			if not intelligent_chunks:
				logger.warning(f'[index_document_to_chroma] No chunks created')
				Document.objects.filter(pk=document.pk).update(
					index_status=Document.IndexStatus.FAILED,
					index_error='Không tạo được chunk nào.',
					indexed_chunks=0,
				)
				return 0

		vector_items = []
		file_name = Path(str(document.file)).name if document.file else ''
		
		enable_structure = config('ENABLE_STRUCTURE_DETECTION', default='True').lower() in ['true', '1', 'yes']

		for index, chunk_data in enumerate(intelligent_chunks):
			raw_chunk_text = normalize_ocr_text(chunk_data.get('chunk', ''))
			chunk_type = normalize_ocr_text(str(chunk_data.get('chunk_type', 'Khác')))
			context_score = normalize_ocr_text(str(chunk_data.get('context_score', 'high')))
			
			if not raw_chunk_text.strip():
				continue
			chunk_metadata = {
				'project_id': document.chat_session.project_id,
				'chat_session_id': document.chat_session_id,
				'document_id': document.id,
				'file_name': file_name,
				'chunk_index': index,
				'chunk_type': str(chunk_type),
				'context_score': str(context_score),
			}
			
			final_chunk_text = raw_chunk_text
			
			if enable_structure and len(raw_chunk_text) >= 100:
				logger.info(f'[index_document_to_chroma] Nhận diện cấu trúc cho chunk {index+1}/{len(intelligent_chunks)}')
				struct_data = rag_svc.detect_document_structure(raw_chunk_text)
				
				# Trích xuất các trường hợp lệ
				section = struct_data.get('section')
				agency = struct_data.get('agency')
				deadline = struct_data.get('deadline')
				signer = struct_data.get('signer')
				
				# Lưu vào metadata (ChromaDB chỉ nhận string, int, float, bool)
				if section: chunk_metadata['section'] = str(section)
				if agency: chunk_metadata['agency'] = str(agency)
				if deadline: chunk_metadata['deadline'] = str(deadline)
				if signer: chunk_metadata['signer'] = str(signer)
				
				# Tạo header thông tin để nối vào đầu chunk text (giúp LLM dễ đọc)
				header_parts = []
				if section: header_parts.append(f"Cấu trúc: {section}")
				if agency: header_parts.append(f"Cơ quan: {agency}")
				if signer: header_parts.append(f"Người ký: {signer}")
				if deadline: header_parts.append(f"Thời hạn: {deadline}")
				
				if header_parts:
					final_chunk_text = f"[{' | '.join(header_parts)}]\n{raw_chunk_text}"

			# Nối thêm chunk_type và context_score vào cuối chunk text nếu là intelligent chunk
			if enable_intelligent_chunking and chunk_type != 'None':
				final_chunk_text += f"\n[Phân loại: {chunk_type} | Độ rõ ràng ngữ cảnh: {context_score}]"
			final_chunk_text = normalize_ocr_text(final_chunk_text)

			vector_items.append(
				{
					'id': f'{document.id}_{index}',
					'text': final_chunk_text,
					'metadata': chunk_metadata,
				}
			)

		logger.info(f'[index_document_to_chroma] Vector items prepared: {len(vector_items)}')
		logger.info(f'[index_document_to_chroma] Calling ChromaService.upsert_chunks')
		chroma = ChromaService()
		chroma.upsert_chunks(project_id=document.chat_session.project_id, chunks=vector_items)
		logger.info(f'[index_document_to_chroma] Upsert complete')
		Document.objects.filter(pk=document.pk).update(
			index_status=Document.IndexStatus.INDEXED,
			indexed_chunks=len(vector_items),
			index_error='',
			indexed_at=django_timezone.now(),
		)
		logger.info(f'[index_document_to_chroma] Document status updated to INDEXED')
		return len(vector_items)
	except Exception as exc:
		logger.error(f'[index_document_to_chroma] Exception in index: {exc}', exc_info=True)
		Document.objects.filter(pk=document.pk).update(
			index_status=Document.IndexStatus.FAILED,
			index_error=str(exc),
			indexed_chunks=0,
		)
		logger.error(f'[index_document_to_chroma] Saved error status to document')
		raise

