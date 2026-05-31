import pytest

from apps.chatbot.models import ChatSession
from apps.documents.models import Document
from apps.documents.services import index_document_to_chroma
from apps.projects.models import Project


@pytest.fixture
def document(user):
    project = Project.objects.create(owner=user, name='Project')
    session = ChatSession.objects.create(project=project, user=user, title='Chat')
    return Document.objects.create(
        chat_session=session,
        uploaded_by=user,
        title='VanBan.pdf',
        file_type=Document.FileType.PDF,
        extracted_text='Số: 1744/VPCP-CN\nNội dung văn bản hành chính.\nNguyễn Văn Thắng',
    )


def disable_llm_features(monkeypatch):
    def fake_config(key, default=None, **kwargs):
        if key in {'ENABLE_INTELLIGENT_CHUNKING', 'ENABLE_STRUCTURE_DETECTION'}:
            return 'False'
        return default

    monkeypatch.setattr('apps.documents.services.config', fake_config)


@pytest.mark.django_db
def test_index_document_sets_indexed_status_and_chunk_count(document, monkeypatch):
    disable_llm_features(monkeypatch)
    captured = {}

    class FakeChromaService:
        def upsert_chunks(self, project_id, chunks):
            captured['project_id'] = project_id
            captured['chunks'] = chunks

    monkeypatch.setattr('apps.documents.services.ChromaService', FakeChromaService)

    chunk_count = index_document_to_chroma(document, chunk_size=40, overlap=0)
    document.refresh_from_db()

    assert chunk_count > 0
    assert document.index_status == Document.IndexStatus.INDEXED
    assert document.indexed_chunks == chunk_count
    assert document.index_error == ''
    assert document.indexed_at is not None
    assert captured['project_id'] == document.chat_session.project_id
    assert len(captured['chunks']) == chunk_count


@pytest.mark.django_db
def test_index_document_marks_failed_when_no_chunks_created(document, monkeypatch):
    disable_llm_features(monkeypatch)
    monkeypatch.setattr('apps.documents.services.chunk_administrative_text', lambda **kwargs: [])

    chunk_count = index_document_to_chroma(document)
    document.refresh_from_db()

    assert chunk_count == 0
    assert document.index_status == Document.IndexStatus.FAILED
    assert document.indexed_chunks == 0
    assert 'chunk' in document.index_error.lower()


@pytest.mark.django_db
def test_index_document_marks_failed_when_vector_store_raises(document, monkeypatch):
    disable_llm_features(monkeypatch)

    class FailingChromaService:
        def upsert_chunks(self, project_id, chunks):
            raise RuntimeError('vector store unavailable')

    monkeypatch.setattr('apps.documents.services.ChromaService', FailingChromaService)

    with pytest.raises(RuntimeError, match='vector store unavailable'):
        index_document_to_chroma(document, chunk_size=40, overlap=0)

    document.refresh_from_db()
    assert document.index_status == Document.IndexStatus.FAILED
    assert document.indexed_chunks == 0
    assert 'vector store unavailable' in document.index_error
