"""Xây dựng prompt cho QA và tóm tắt.

Tập trung các prompt ở một chỗ để dễ dàng review và cập nhật templates.

Các hàm prompt trả về plain text; chúng không gọi LLM trực tiếp.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Union


SEPARATOR = "\n---\n"


def build_qa_prompt(
	question: str,
	contexts: Iterable[Union[str, Dict[str, str]]],
	instruction: str | None = None,
	max_context_chars: int = 5000,
) -> str:
	"""Xây dựng prompt QA bằng cách kết hợp context đã lấy được và câu hỏi.

	- contexts: danh sách các đoạn text hoặc dict {text, file_name} được sắp xếp
	  theo độ liên quan (tốt nhất trước). Nếu là dict, file_name sẽ được prefix
	  vào đoạn text để LLM biết nguồn gốc.
	- instruction: hướng dẫn tùy chọn để thêm vào
	- max_context_chars: giới hạn tổng độ dài context (ký tự)
	"""
	parts: List[str] = []
	if instruction:
		parts.append(instruction)

	# Kết hợp contexts với separators, giữ dưới max_context_chars
	combined = ''
	for c in contexts:
		# Hỗ trợ cả plain string (backward-compatible) và dict {text, file_name}
		if isinstance(c, dict):
			text = c.get('text', '')
			file_name = c.get('file_name', '')
			if file_name:
				entry = f'[Nguồn: {file_name}]\n{text}'
			else:
				entry = text
		else:
			entry = c if c else ''

		if not entry:
			continue
		if len(combined) + len(entry) + len(SEPARATOR) > max_context_chars:
			break
		if combined:
			combined += SEPARATOR
		combined += entry

	if combined:
		parts.append('Ngữ cảnh cho câu hỏi:\n' + combined)

	parts.append('Câu hỏi: ' + question)
	parts.append('Lưu ý: Chỉ làm theo yêu cầu của QA & Summary Agent, sử dụng duy nhất các chunk được cung cấp ở trên.')

	return '\n\n'.join(parts)


def build_summary_prompt(text: str, instruction: str | None = None) -> str:
	"""Xây dựng prompt cho tóm tắt một đoạn text/tài liệu."""
	parts: List[str] = []
	if instruction:
		parts.append(instruction)
	parts.append('Tóm tắt đoạn text sau thành 3-5 điểm chính:')
	parts.append(text)
	return '\n\n'.join(parts)


def get_default_instruction() -> str:
	"""Hướng dẫn mặc định cho LLM khi trả lời câu hỏi và tóm tắt (QA & Summary Agent)."""
	return """Bạn là QA & Summary Agent.

Quy tắc:
- Chỉ dùng thông tin từ các chunk (đoạn ngữ cảnh) được truy xuất ở trên.
- KHÔNG dùng kiến thức bên ngoài.
- KHÔNG suy diễn.
- KHÔNG đoán.
- KHÔNG tự bổ sung thông tin.

Nếu thông tin trong các chunk bị thiếu hoặc không đủ để trả lời câu hỏi, hãy trả về đúng nguyên văn:
"Không tìm thấy thông tin."

Nếu có thông tin, MỖI câu trả lời bắt buộc phải theo ĐÚNG định dạng 3 phần sau:

Câu trả lời:
[Trình bày câu trả lời của bạn]

Trích dẫn:
"[Trích dẫn nguyên văn một đoạn hoặc một câu từ ngữ cảnh]"

Độ tin cậy:
[Cao / Trung bình / Thấp]"""


def get_cleaning_agent_instruction() -> str:
	"""Prompt cho tác vụ làm sạch text từ OCR/PDF."""
	return """Bạn là Document Cleaning Agent.

Nhiệm vụ:
Làm sạch dữ liệu được trích xuất từ:
- OCR
- PDF parser
- DOCX parser

Dữ liệu có thể chứa:
- header
- footer
- số trang
- watermark
- QR
- email
- metadata
- chữ ký số
- thời gian scan
- dữ liệu lặp
- text lỗi

Quy tắc:
Nếu một đoạn xuất hiện lặp nhiều trang: xem như header/footer.
Giảm hoặc loại bỏ:
- Trang x/y
- Cổng thông tin điện tử
- QR
- email hệ thống
- thời gian ký số
- watermark

Không thay đổi nội dung chính.
Không suy luận thêm nội dung bên ngoài.
Chỉ trả về phần text đã làm sạch, KHÔNG GIẢI THÍCH, KHÔNG CHÀO HỎI."""

def build_cleaning_prompt(text: str) -> str:
	"""Xây dựng prompt để làm sạch đoạn text."""
	return f"{get_cleaning_agent_instruction()}\n\nĐoạn văn bản cần làm sạch:\n{text}\n\nĐoạn văn bản sau khi làm sạch:"


def get_structure_agent_instruction() -> str:
	"""Prompt cho tác vụ nhận diện cấu trúc văn bản hành chính."""
	return """Bạn là Structure Detection Agent.

Nhiệm vụ:
Nhận diện cấu trúc văn bản hành chính.

Phát hiện:
- Chương
- Mục
- Điều
- Khoản
- Điểm

Nhận diện:
- cơ quan
- nhiệm vụ
- thời hạn
- người ký (Lưu ý: Người ký thường nằm ở cuối văn bản dưới chức danh như Bộ trưởng, Thứ trưởng, Chủ nhiệm. KHÔNG nhầm lẫn với những lãnh đạo được nhắc tên trong nội dung văn bản mang tính chất "có ý kiến chỉ đạo").
- văn bản liên quan

Không suy diễn.
Nếu thiếu: đánh dấu null.

Trả về duy nhất định dạng JSON sau, không có text nào khác ngoài JSON:
{
 "section": "Chương/Mục/Điều/Khoản/Điểm tương ứng hoặc null",
 "agency": "Tên cơ quan hoặc null",
 "deadline": "Thời hạn hoặc null",
 "signer": "Người ký hoặc null",
 "content": "Nội dung chính hoặc null"
}"""

def build_structure_prompt(text: str) -> str:
	"""Xây dựng prompt để nhận diện cấu trúc đoạn text."""
	return f"{get_structure_agent_instruction()}\n\nĐoạn văn bản cần nhận diện:\n{text}"

def get_chunking_agent_instruction() -> str:
	"""Prompt cho tác vụ chia chunk thông minh bằng LLM."""
	return """Bạn là Chunk Intelligence Agent.

Nhiệm vụ:
Phân tách văn bản hành chính thành các đoạn (chunk) nhỏ để lưu trữ dữ liệu.
Không chia chunk theo số ký tự cố định.

Ưu tiên giữ nguyên:
- Điều
- Khoản
- Mục
- nhiệm vụ
- thời hạn

Không cắt:
Điều 1...
sang chunk khác. Nếu đoạn liên quan chặt: giữ cùng chunk.

Nếu chunk bị mất ngữ cảnh (không rõ ràng): đánh dấu context_score="low", ngược lại là "high" hoặc "medium".

TRẢ VỀ DUY NHẤT một MẢNG JSON (JSON array) các đối tượng theo đúng định dạng sau, KHÔNG GIẢI THÍCH GÌ THÊM:
[
 {
  "chunk": "nội dung nguyên văn của đoạn text",
  "chunk_type": "Điều / Khoản / Mục / Nhiệm vụ / Khác",
  "context_score": "high / medium / low"
 }
]"""

def build_chunking_prompt(text: str) -> str:
	"""Xây dựng prompt để chia chunk một đoạn text."""
	return f"{get_chunking_agent_instruction()}\n\nĐoạn văn bản cần phân tách:\n{text}"

def get_retrieval_agent_instruction() -> str:
	"""Prompt cho tác vụ đánh giá và xếp hạng lại chunk (Retrieval Agent)."""
	return """Bạn là Retrieval Agent.

Nhiệm vụ:
Đánh giá độ liên quan của đoạn văn bản (chunk) đối với câu hỏi của người dùng.

Ưu tiên:
1. tên cơ quan: Bộ, UBND, Sở, Cục
2. cấu trúc: Điều, Khoản, Mục
3. nhiệm vụ: giao, chỉ đạo, rà soát, nghiên cứu, thực hiện
4. thời hạn: trước ngày, hoàn thành

Giảm ưu tiên:
- header, footer, số trang
- QR, metadata, thời gian ký

Không trả lời câu hỏi.

Chỉ trả về DUY NHẤT một MẢNG JSON theo định dạng sau:
[
 {
  "chunk": "nội dung đoạn text",
  "score": điểm từ 0 đến 100,
  "reason": "lý do đánh giá ngắn gọn"
 }
]"""

def build_retrieval_prompt(question: str, text: str) -> str:
	"""Xây dựng prompt để đánh giá một chunk so với câu hỏi."""
	return f"{get_retrieval_agent_instruction()}\n\nCâu hỏi: {question}\n\nĐoạn văn bản cần đánh giá:\n{text}"

def get_validation_agent_instruction() -> str:
	"""Prompt cho tác vụ Validation Agent (Kiểm tra chéo và bắt lỗi)."""
	return """Bạn là Validation Agent.

Nhiệm vụ:
Kiểm tra tính hợp lệ của dữ liệu, văn bản hoặc metadata được trích xuất.

Kiểm tra các lỗi sau:
- thời hạn mâu thuẫn
- tên người sai (ví dụ nhầm tổ chức thành người)
- metadata bị xem là nội dung
- OCR lỗi
- text đứt đoạn
- chunk sai ngữ cảnh

Ví dụ:
Người ký: CỔNG THÔNG TIN ĐIỆN TỬ CHÍNH PHỦ
-> Có khả năng là chữ ký số. Không kết luận người ký.

Nếu nghi ngờ bất cứ điều gì: đánh dấu confidence="low".

Trả về DUY NHẤT định dạng JSON sau:
{
 "is_valid": true/false,
 "confidence": "high/low",
 "issues": ["danh sách lỗi phát hiện hoặc rỗng"],
 "corrected_data": "Dữ liệu/metadata đã được sửa lại cho đúng, hoặc null"
}"""

def build_validation_prompt(data_to_validate: str) -> str:
	"""Xây dựng prompt để kiểm tra tính hợp lệ."""
	return f"{get_validation_agent_instruction()}\n\nDữ liệu cần kiểm tra:\n{data_to_validate}"

__all__ = [
	'build_qa_prompt', 
	'build_summary_prompt', 
	'get_default_instruction', 
	'get_cleaning_agent_instruction', 
	'build_cleaning_prompt',
	'get_structure_agent_instruction',
	'build_structure_prompt',
	'get_chunking_agent_instruction',
	'build_chunking_prompt',
	'get_retrieval_agent_instruction',
	'build_retrieval_prompt',
	'get_validation_agent_instruction',
	'build_validation_prompt'
]



