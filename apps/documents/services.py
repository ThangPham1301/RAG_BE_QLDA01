from __future__ import annotations

import logging
from pathlib import Path

from django.utils import timezone as django_timezone

from apps.chatbot.chroma_service import ChromaService

from .models import Document
from .parser import chunk_text, extract_text_from_pdf

logger = logging.getLogger(__name__)


def _extract_text_from_docx(path: str) -> str:
	try:
		from docx import Document as DocxDocument
	except Exception:
		return ''

	doc = DocxDocument(path)
	parts = []
	for p in doc.paragraphs:
		if p.text:
			parts.append(p.text)
	return '\n'.join(parts)


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
			text = _extract_text_from_docx(str(abs_path))
			logger.info(f'[populate_document_extracted_text] DOCX extraction result: {len(text or "")} chars')
		elif file_type == Document.FileType.TXT or file_type == 'txt':
			logger.info(f'[populate_document_extracted_text] Extracting as TXT')
			text = _extract_text_from_txt(str(abs_path))
			logger.info(f'[populate_document_extracted_text] TXT extraction result: {len(text or "")} chars')
		else:
			logger.warning(f'[populate_document_extracted_text] Unknown file type: {file_type}, returning empty')
			text = ''
			
	except Exception as e:
		logger.error(f'[populate_document_extracted_text] Extraction failed: {e}', exc_info=True)
		raise

	if not text or not text.strip():
		logger.warning(f'[populate_document_extracted_text] Extracted text is empty or whitespace-only')
	
	document.extracted_text = text or ''
	document.save(update_fields=['extracted_text'])
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

		logger.info(f'[index_document_to_chroma] Calling chunk_text with chunk_size={chunk_size}')
		chunks = chunk_text(text=text, chunk_size=chunk_size, overlap=overlap)
		logger.info(f'[index_document_to_chroma] Chunks created: {len(chunks)}')
		if not chunks:
			logger.warning(f'[index_document_to_chroma] No chunks created')
			Document.objects.filter(pk=document.pk).update(
				index_status=Document.IndexStatus.FAILED,
				index_error='Không tạo được chunk nào.',
				indexed_chunks=0,
			)
			return 0

		vector_items = []
		file_name = Path(str(document.file)).name if document.file else ''
		for index, chunk in enumerate(chunks):
			vector_items.append(
				{
					'id': f'{document.id}_{index}',
					'text': chunk,
					'metadata': {
						'project_id': document.chat_session.project_id,
						'chat_session_id': document.chat_session_id,
						'document_id': document.id,
						'file_name': file_name,
						'page': None,
						'chunk_index': index,
					},
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

