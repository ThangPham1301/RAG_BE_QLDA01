"""Xây dựng prompt cho QA và tóm tắt.

Tập trung các prompt ở một chỗ để dễ dàng review và cập nhật templates.

Các hàm prompt trả về plain text; chúng không gọi LLM trực tiếp.
"""
from __future__ import annotations

from typing import Iterable, List


SEPARATOR = "\n---\n"


def build_qa_prompt(question: str, contexts: Iterable[str], instruction: str | None = None, max_context_chars: int = 5000) -> str:
	"""Xây dựng prompt QA bằng cách kết hợp context đã lấy được và câu hỏi.

	- contexts: danh sách các đoạn text được sắp xếp theo độ liên quan (tốt nhất trước)
	- instruction: hướng dẫn tùy chọn để thêm vào
	- max_context_chars: giới hạn tổng độ dài context (ký tự)
	"""
	parts: List[str] = []
	if instruction:
		parts.append(instruction)

	# Kết hợp contexts với separators, giữ dưới max_context_chars
	combined = ''
	for c in contexts:
		if not c:
			continue
		if len(combined) + len(c) + len(SEPARATOR) > max_context_chars:
			break
		if combined:
			combined += SEPARATOR
		combined += c

	if combined:
		parts.append('Ngữ cảnh cho câu hỏi:\n' + combined)

	parts.append('Câu hỏi: ' + question)
	parts.append('Vui lòng trả lời một cách ngắn gọn và đi kèm với trích dẫn nếu có liên quan.')

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
	"""Hướng dẫn mặc định cho LLM khi trả lời câu hỏi."""
	return """Bạn là một trợ lý ảo hỗ trợ giải đáp các câu hỏi về tài liệu.
- Trả lời dựa trên context được cung cấp
- Nếu không tìm thấy thông tin, hãy nói rõ "Không có thông tin"
- Sử dụng tiếng Việt tự nhiên và chính xác
- Tập trung vào câu hỏi, tránh những thông tin không liên quan"""


__all__ = ['build_qa_prompt', 'build_summary_prompt', 'get_default_instruction']
