"""LLM service wrapper to call a local Ollama server.

This module exposes a simple, testable interface for generating text
from a local Ollama instance running models such as Qwen3-vl:4b.

The implementation is intentionally small and dependency-light: it uses
`requests` for HTTP calls and configuration via environment variables.

Production notes:
- Keep calls idempotent and handle network errors.
- Prefer calling with a timeout and non-blocking (streaming) option when needed.
"""
from __future__ import annotations

import os
import json
import logging
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)


class LLMService:
	"""Simple wrapper around an Ollama local API.

	Configuration (via env):
	- OLLAMA_URL: base url (default http://localhost:11434)
	- OLLAMA_MODEL: model name (default 'qwen3-vl:4b')
	"""

	def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
		self.base_url = base_url or os.environ.get('OLLAMA_URL', 'http://localhost:11434')
		self.model = model or os.environ.get('OLLAMA_MODEL', 'qwen3-vl:4b')
		# Default timeout (seconds) for HTTP calls to Ollama. Can be overridden by env OLLAMA_TIMEOUT
		try:
			self.default_timeout = int(os.environ.get('OLLAMA_TIMEOUT', '60'))
		except Exception:
			self.default_timeout = 60
		try:
			self.default_num_predict = int(os.environ.get('OLLAMA_NUM_PREDICT', '256'))
		except Exception:
			self.default_num_predict = 256
		try:
			self.default_num_ctx = int(os.environ.get('OLLAMA_NUM_CTX', '2048'))
		except Exception:
			self.default_num_ctx = 2048
		self.default_keep_alive = os.environ.get('OLLAMA_KEEP_ALIVE', '30m')

	def generate(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.0, options: Optional[Dict[str, Any]] = None, timeout: Optional[int] = None) -> str:
		"""Generate text from the configured model.

		This uses the Ollama HTTP API: POST /api/generate with streaming response.
		Each line is a JSON object containing a partial response.

		Returns the generated text (concatenated) on success.
		Raises requests.RequestException on transport errors.
		"""
		url = f"{self.base_url.rstrip('/')}/api/generate"
		ollama_options: Dict[str, Any] = {
			'temperature': temperature,
			'num_predict': max_tokens if max_tokens is not None else self.default_num_predict,
			'num_ctx': self.default_num_ctx,
		}
		if options:
			ollama_options.update(options)

		payload = {
			'model': self.model,
			'prompt': prompt,
			'stream': False,  # Disable streaming for simpler parsing
			'temperature': temperature,
			'options': ollama_options,
			'keep_alive': self.default_keep_alive,
		}

		logger.debug('LLM generate request payload keys: %s', list(payload.keys()))

		# Use configured default timeout if not provided per-call
		use_timeout = timeout if timeout is not None else self.default_timeout
		try:
			resp = requests.post(url, json=payload, timeout=use_timeout, stream=False)
			resp.raise_for_status()
			
			# Parse JSON response
			data = resp.json()
			
			# Ollama returns: {'model': '...', 'response': '...', 'done': true/false, ...}
			if isinstance(data, dict):
				if 'response' in data:
					response_text = (data.get('response') or '').strip()
					if response_text:
						return response_text

					# Compatibility fallback: some Ollama/model combos may return empty text with aggressive options.
					logger.warning('LLM returned empty response, retrying once with compatibility payload')
					fallback_payload = {
						'model': self.model,
						'prompt': prompt,
						'stream': False,
						'temperature': temperature,
					}
					fallback_resp = requests.post(url, json=fallback_payload, timeout=use_timeout, stream=False)
					fallback_resp.raise_for_status()
					fallback_data = fallback_resp.json()
					if isinstance(fallback_data, dict):
						return (fallback_data.get('response') or '').strip()
					return str(fallback_data)
				# Fallback: return stringified JSON if nothing matched
				logger.warning('Unexpected LLM response shape, keys: %s', list(data.keys()))
				return str(data)
			
			return str(data)
		except json.JSONDecodeError as e:
			logger.error(f'Failed to parse LLM response JSON: {e}')
			raise
		except requests.exceptions.ReadTimeout as e:
			logger.error(f'LLM request timed out after {use_timeout}s: {e}', exc_info=True)
			raise
		except Exception as e:
			logger.error(f'LLM generation failed: {e}', exc_info=True)
			raise
