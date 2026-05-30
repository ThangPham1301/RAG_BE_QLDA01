from apps.chatbot.prompt_service import (
    SEPARATOR,
    build_chunking_prompt,
    build_cleaning_prompt,
    build_qa_prompt,
    build_retrieval_prompt,
    build_structure_prompt,
    build_summary_prompt,
    build_validation_prompt,
)


def test_build_qa_prompt_includes_instruction_sources_question_and_separator():
    prompt = build_qa_prompt(
        question='What is the deadline?',
        contexts=[
            {'file_name': 'plan.pdf', 'text': 'Deadline is Friday.'},
            'Budget is approved.',
        ],
        instruction='Answer from sources only.',
    )

    assert 'Answer from sources only.' in prompt
    assert '[Ngu' in prompt
    assert 'plan.pdf' in prompt
    assert SEPARATOR in prompt
    assert 'What is the deadline?' in prompt


def test_build_qa_prompt_respects_max_context_chars():
    prompt = build_qa_prompt('Question?', ['short', 'this entry is too long'], max_context_chars=12)

    assert 'short' in prompt
    assert 'this entry is too long' not in prompt


def test_summary_and_agent_prompts_embed_input_text():
    assert 'document text' in build_summary_prompt('document text')
    assert 'dirty text' in build_cleaning_prompt('dirty text')
    assert 'structured text' in build_structure_prompt('structured text')
    assert 'chunk text' in build_chunking_prompt('chunk text')
    assert 'retrieval text' in build_retrieval_prompt('question', 'retrieval text')
    assert 'payload' in build_validation_prompt('payload')
