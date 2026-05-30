from django.core.files.uploadedfile import SimpleUploadedFile

from apps.documents.field_validators import is_valid_extracted_field, is_valid_signer_field
from apps.documents.serializers import DocumentUploadSerializer
from apps.documents.text_normalizer import layout_to_text, normalize_lines, normalize_spacing


def test_normalize_spacing_collapses_extra_spaces_and_blank_lines():
    assert normalize_spacing('  A   B \r\n\r\n\r\n C  , D ') == 'A B\n\nC, D'


def test_normalize_lines_drops_empty_normalized_lines():
    assert normalize_lines(['  First  ', '', '   ', 'Second']) == ['First', 'Second']


def test_layout_to_text_reads_page_lines_and_ignores_empty_text():
    layout = {
        'pages': [
            {'lines': [{'text': ' Page 1 line '}, {'text': ''}]},
            {'lines': [{'text': 'Page 2 line'}]},
        ]
    }

    assert layout_to_text(layout) == 'Page 1 line\n\nPage 2 line'


def test_field_validators_require_found_status_value_and_confidence():
    assert is_valid_extracted_field({'status': 'found', 'value': 'A', 'confidence': 0.5}) is True
    assert is_valid_extracted_field({'status': 'missing', 'value': 'A', 'confidence': 0.9}) is False
    assert is_valid_signer_field({'status': 'found', 'value': 'Signer', 'confidence': 0.55, 'evidence': ['signed']}) is True
    assert is_valid_signer_field({'status': 'found', 'value': 'Signer', 'confidence': 0.55, 'evidence': []}) is False


def test_document_upload_serializer_rejects_unsupported_file_extension():
    serializer = DocumentUploadSerializer(data={
        'chat_session_id': 1,
        'file': SimpleUploadedFile('malware.exe', b'bad'),
    })

    assert serializer.is_valid() is False
    assert 'file' in serializer.errors
