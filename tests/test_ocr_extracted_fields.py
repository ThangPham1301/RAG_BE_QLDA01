from apps.documents.admin_doc_extractor import extract_administrative_fields, extract_signer
from apps.documents.field_validators import is_valid_extracted_field, is_valid_signer_field


def make_layout(lines, width=800, height=1000):
    return {
        'pages': [{
            'page': 1,
            'width': width,
            'height': height,
            'lines': lines,
        }]
    }


def test_extract_signer_uses_lower_right_signature_region_not_body_names():
    layout = make_layout([
        {'text': 'Thủ tướng Chính phủ Phạm Minh Chính có ý kiến như sau:', 'bbox': [80, 300, 620, 330], 'confidence': 0.99},
        {'text': 'Nơi nhận:', 'bbox': [80, 760, 180, 785], 'confidence': 0.98},
        {'text': '- Phạm Minh Chính;', 'bbox': [80, 790, 260, 815], 'confidence': 0.98},
        {'text': 'KT. BỘ TRƯỞNG, CHỦ NHIỆM', 'bbox': [500, 720, 760, 750], 'confidence': 0.98},
        {'text': 'PHÓ CHỦ NHIỆM', 'bbox': [540, 750, 720, 780], 'confidence': 0.98},
        {'text': 'Nguyễn Văn Thắng', 'bbox': [555, 890, 725, 925], 'confidence': 0.99},
    ])

    signer = extract_signer(layout)

    assert signer['status'] == 'found'
    assert signer['value'] == 'Nguyễn Văn Thắng'
    assert signer['source'] == 'signature_region'
    assert 'Phạm Minh Chính' not in signer['value']
    assert is_valid_signer_field(signer) is True


def test_extract_administrative_fields_reads_document_number_and_date_from_header():
    fields = extract_administrative_fields(
        {},
        plain_text='\n'.join([
            'VĂN PHÒNG CHÍNH PHỦ',
            'Số: 1744/VPCP-CN Hà Nội, ngày 27 tháng 02 năm 2026',
            'Kính gửi: Bộ trưởng Bộ Xây dựng.',
            'KT. BỘ TRƯỞNG, CHỦ NHIỆM',
            'PHÓ CHỦ NHIỆM',
            'Nguyễn Văn Thắng',
        ]),
    )

    assert fields['document_number']['value'] == '1744/VPCP-CN'
    assert fields['place_date']['value'] == 'Hà Nội, ngày 27 tháng 02 năm 2026'
    assert fields['signer']['value'] == 'Nguyễn Văn Thắng'
    assert is_valid_extracted_field(fields['document_number']) is True
    assert is_valid_extracted_field(fields['place_date']) is True


def test_signer_is_not_found_when_only_recipient_names_exist():
    signer = extract_signer(
        {},
        plain_text='\n'.join([
            'Kính gửi: Bộ trưởng Bộ Xây dựng.',
            'Nơi nhận:',
            '- Nguyễn Văn A;',
            '- Trần Văn B;',
            'Lưu: VT, CN.',
        ]),
    )

    assert signer['status'] == 'not_found'
    assert is_valid_signer_field(signer) is False
