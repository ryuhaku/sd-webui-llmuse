import base64
import io
import json
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gradio as gr
import requests
from PIL import Image, ImageOps
from modules import scripts, shared
from modules.scripts import OnComponent

LM_STUDIO_BASE = "http://localhost:1234"

EXTENSION_DIR = Path(__file__).resolve().parent.parent
PRESETS_FILE = EXTENSION_DIR / "presets.json"
SETTINGS_FILE = EXTENSION_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "model": "",
    "vision_model": "",
    "temperature": 0.8,
    "timeout": 30,
    "gpu_ttl_enabled": False,
    "gpu_ttl": 300,
    "lm_url": "http://localhost:1234",
    "auto_send": False,
    "send_mode": "append",
    "auto_generate": False,
    "continuous_generate": False,
    "loop_delay": 500,
    "batch_vision_enabled": False,
    "img2img_instruction": "",
    "last_preset": "",
    "last_preset_txt2img": "",
    "last_preset_img2img": "",
}


# ── デフォルトプリセット（初回起動時のみ presets.json に書き込む）──────────
DEFAULT_PRESETS = {
    "Simple": (
        "You are an AI that generates English prompts for Stable Diffusion (anime/illustration models).\n\n"
        "Rules:\n"
        "- Translate the Japanese input into English faithfully without changing its meaning.\n"
        "- Do not add any elements not present in the input.\n"
        "- Output only the prompt text.\n"
        "- Do not write greetings, explanations, preambles, or annotations."
    ),
    "Normal": (
        "You are an AI that generates English prompts for Stable Diffusion (anime/illustration models).\n\n"
        "Rules:\n"
        "- Translate the Japanese input into English and naturally supplement lighting, atmosphere, and quality tags within reasonable bounds.\n"
        "- Add only minimal details to characters and backgrounds based on the input.\n"
        "- Output as an English prompt of approximately 60–80 words.\n"
        "- Output only the prompt text.\n"
        "- Do not write greetings, explanations, preambles, or annotations."
    ),
    "Detail": (
        "You are an AI that generates English prompts for Stable Diffusion (anime/illustration models).\n\n"
        "Rules:\n"
        "- Translate the Japanese input into English and add detailed descriptions of character appearance, outfit, expression, pose, background, lighting, camera angle, art style, and quality tags.\n"
        "- Actively imagine and supplement elements not present in the input.\n"
        "- Output as an English prompt of 100 words or more.\n"
        "- Output only the prompt text.\n"
        "- Do not write greetings, explanations, preambles, or annotations."
    ),
}

VISION_SYSTEM_PREFIX = """You are a vision-language assistant that creates English prompts for Stable Diffusion img2img.
Analyze the supplied source image, including the subject, appearance, clothing, expression, pose, composition, camera angle, background, lighting, colors, and visual style.
Apply the user's requested changes while preserving source-image details that the user did not ask to change.
Return only the final English Stable Diffusion prompt. Do not output analysis, explanations, headings, notes, or quotation marks.

The following preset controls the desired level of detail:
"""


# ── 設定管理 ────────────────────────────────────────────────────────────────
def _load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return {**DEFAULT_SETTINGS, **json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()


def _save_settings(data: dict):
    s = _load_settings()
    if "model" in data:
        s["model"] = str(data["model"] or "")
    if "vision_model" in data:
        s["vision_model"] = str(data["vision_model"] or "")
    if "temperature" in data:
        s["temperature"] = float(data["temperature"])
    if "timeout" in data:
        s["timeout"] = max(5, int(data["timeout"]))
    if "gpu_ttl_enabled" in data:
        s["gpu_ttl_enabled"] = bool(data["gpu_ttl_enabled"])
    if "gpu_ttl" in data:
        s["gpu_ttl"] = max(1, int(data["gpu_ttl"]))
    if "lm_url" in data:
        s["lm_url"] = str(data["lm_url"]).rstrip("/") or LM_STUDIO_BASE
    if "auto_send" in data:
        s["auto_send"] = bool(data["auto_send"])
    if "send_mode" in data:
        s["send_mode"] = "replace" if str(data["send_mode"]) == "replace" else "append"
    if "auto_generate" in data:
        s["auto_generate"] = bool(data["auto_generate"])
    if "continuous_generate" in data:
        s["continuous_generate"] = bool(data["continuous_generate"])
    if "loop_delay" in data:
        s["loop_delay"] = max(0, int(data["loop_delay"]))
    if "batch_vision_enabled" in data:
        s["batch_vision_enabled"] = bool(data["batch_vision_enabled"])
    if "img2img_instruction" in data:
        s["img2img_instruction"] = str(data["img2img_instruction"] or "")
    if "last_preset" in data:
        s["last_preset"] = str(data["last_preset"] or "")
    if "last_preset_txt2img" in data:
        s["last_preset_txt2img"] = str(data["last_preset_txt2img"] or "")
    if "last_preset_img2img" in data:
        s["last_preset_img2img"] = str(data["last_preset_img2img"] or "")
    SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    return s


def _save_last_preset(name: str, tab: str):
    key = "last_preset_img2img" if tab == "img2img" else "last_preset_txt2img"
    _save_settings({key: name, "last_preset": name})


# ── プリセット管理 ──────────────────────────────────────────────────────────
def _load_presets() -> dict:
    if PRESETS_FILE.exists():
        try:
            return json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    PRESETS_FILE.write_text(json.dumps(DEFAULT_PRESETS, ensure_ascii=False, indent=2), encoding="utf-8")
    return DEFAULT_PRESETS.copy()


def _save_presets(presets: dict):
    PRESETS_FILE.write_text(json.dumps(presets, ensure_ascii=False, indent=2), encoding="utf-8")


def _initial_preset(settings: dict, presets: dict, tab: str) -> str:
    names = list(presets.keys())
    tab_key = "last_preset_img2img" if tab == "img2img" else "last_preset_txt2img"
    candidate = settings.get(tab_key) or settings.get("last_preset") or ""
    return candidate if candidate in presets else names[0]


# ── LM Studio API ───────────────────────────────────────────────────────────
@dataclass
class LMResult:
    text: str = ""
    error: str = ""
    kind: str = ""  # fatal / image / empty / length

    @property
    def ok(self) -> bool:
        return bool(self.text) and not self.error


def _get_models(vision_only: bool = False) -> list:
    """GET /api/v1/models — インストール済みモデルを返す。"""
    try:
        base = _load_settings().get("lm_url", LM_STUDIO_BASE)
        r = requests.get(f"{base}/api/v1/models", timeout=5)
        if r.ok:
            models = [m for m in r.json().get("models", []) if m.get("key") and m.get("type", "llm") == "llm"]
            if vision_only:
                capability_known = any("vision" in (m.get("capabilities") or {}) for m in models)
                if capability_known:
                    models = [m for m in models if (m.get("capabilities") or {}).get("vision") is True]
            return [m["key"] for m in models]
    except Exception:
        pass
    return []


def _unload_all_models(base: str) -> None:
    """GET /api/v1/models で loaded_instances を取得し全インスタンスを解放する。"""
    try:
        r = requests.get(f"{base}/api/v1/models", timeout=5)
        if not r.ok:
            return
        for model in r.json().get("models", []):
            for inst in model.get("loaded_instances", []):
                iid = inst.get("id")
                if iid:
                    requests.post(
                        f"{base}/api/v1/models/unload",
                        json={"instance_id": iid},
                        timeout=10,
                    )
    except Exception:
        pass


def _api_error_message(response: requests.Response) -> str:
    try:
        body = response.json()
        err = body.get("error")
        if isinstance(err, dict):
            msg = err.get("message") or err.get("type")
            if msg:
                return str(msg)[:300]
        if err:
            return str(err)[:300]
    except Exception:
        pass
    return (response.text or response.reason or "Unknown LM Studio error")[:300]


def _ensure_model_loaded(base: str, model_id: str, settings: dict, require_vision: bool = False) -> LMResult:
    if not model_id:
        return LMResult(error="No model selected in LLMuse.", kind="fatal")

    try:
        r = requests.get(f"{base}/api/v1/models", timeout=5)
    except requests.exceptions.ConnectionError:
        return LMResult(error="Cannot connect to LM Studio.", kind="fatal")
    except requests.exceptions.Timeout:
        return LMResult(error="Timed out while checking LM Studio models.", kind="fatal")
    except Exception as e:
        return LMResult(error=f"Failed to check LM Studio models: {e}", kind="fatal")

    if not r.ok:
        return LMResult(
            error=f"Failed to list LM Studio models ({r.status_code}): {_api_error_message(r)}",
            kind="fatal",
        )

    models = r.json().get("models", [])
    selected = next((m for m in models if m.get("key") == model_id), None)
    if selected is None:
        return LMResult(
            error=f"Selected model was not found in LM Studio: {model_id}",
            kind="fatal",
        )
    if selected.get("type", "llm") != "llm":
        return LMResult(error=f"Selected model is not an LLM: {model_id}", kind="fatal")
    vision_capability = (selected.get("capabilities") or {}).get("vision")
    if require_vision and vision_capability is False:
        return LMResult(
            error=f"Selected model does not support image input: {model_id}",
            kind="fatal",
        )
    if selected.get("loaded_instances"):
        return LMResult(text="loaded")

    _unload_all_models(base)
    ttl = settings.get("gpu_ttl", 0) if settings.get("gpu_ttl_enabled") else 0
    payload: dict[str, Any] = {"model": model_id}
    if ttl > 0:
        payload["ttl"] = ttl

    try:
        r = requests.post(f"{base}/api/v1/models/load", json=payload, timeout=120)
    except requests.exceptions.ConnectionError:
        return LMResult(error="Cannot connect to LM Studio while loading the model.", kind="fatal")
    except requests.exceptions.Timeout:
        return LMResult(error=f"Timed out while loading model: {model_id}", kind="fatal")
    except Exception as e:
        return LMResult(error=f"Failed to load model {model_id}: {e}", kind="fatal")

    if not r.ok:
        return LMResult(
            error=f"Failed to load model {model_id} ({r.status_code}): {_api_error_message(r)}",
            kind="fatal",
        )
    return LMResult(text="loaded")


def _strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_response_text(data: dict) -> str:
    content = data["choices"][0]["message"]["content"]
    if isinstance(content, str):
        return _strip_thinking(content)
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
                parts.append(str(item.get("text", "")))
        return _strip_thinking("\n".join(parts))
    return ""


def _call_chat(model_id: str, messages: list, max_tokens: int = 512, require_vision: bool = False) -> LMResult:
    settings = _load_settings()
    base = settings.get("lm_url", LM_STUDIO_BASE)

    ready = _ensure_model_loaded(base, model_id, settings, require_vision=require_vision)
    if not ready.ok:
        return ready

    payload: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "temperature": settings["temperature"],
        "max_tokens": max_tokens,
        "stream": False,
        "enable_thinking": False,
    }
    if settings.get("gpu_ttl_enabled") and settings.get("gpu_ttl", 0) > 0:
        payload["ttl"] = settings["gpu_ttl"]

    try:
        r = requests.post(
            f"{base}/v1/chat/completions",
            json=payload,
            timeout=settings["timeout"],
        )
    except requests.exceptions.ConnectionError:
        return LMResult(error="Cannot connect to LM Studio.", kind="fatal")
    except requests.exceptions.Timeout:
        return LMResult(error=f"LM Studio timed out after {settings['timeout']} seconds.", kind="fatal")
    except Exception as e:
        return LMResult(error=f"LM Studio request failed: {e}", kind="fatal")

    if not r.ok:
        return LMResult(
            error=f"LM Studio returned HTTP {r.status_code}: {_api_error_message(r)}",
            kind="fatal",
        )

    try:
        data = r.json()
        text = _extract_response_text(data)
        finish_reason = ((data.get("choices") or [{}])[0]).get("finish_reason")
    except Exception as e:
        return LMResult(error=f"Invalid LM Studio response: {e}", kind="fatal")

    if finish_reason == "length":
        return LMResult(error="LM Studio output reached the token limit.", kind="length")
    if not text:
        return LMResult(error="LM Studio returned an empty response.", kind="empty")
    return LMResult(text=text)


def _call_chat_with_length_retry(
    model_id: str,
    messages: list,
    initial_max_tokens: int,
    retry_max_tokens: int | None = None,
    require_vision: bool = False,
) -> LMResult:
    result = _call_chat(
        model_id,
        messages,
        max_tokens=initial_max_tokens,
        require_vision=require_vision,
    )
    if result.kind == "length" and retry_max_tokens and retry_max_tokens > initial_max_tokens:
        result = _call_chat(
            model_id,
            messages,
            max_tokens=retry_max_tokens,
            require_vision=require_vision,
        )
        if result.kind == "length":
            return LMResult(
                error=(
                    "LM Studio output was truncated at the token limit even after retry. "
                    f"Increase max_tokens further or shorten the instruction. (retry max_tokens={retry_max_tokens})"
                ),
                kind="length",
            )
    return result


def _call_lm_text(user_input: str, system_prompt: str, model_id: str) -> LMResult:
    if not user_input.strip():
        return LMResult(error="Enter an instruction before running LLMuse.", kind="fatal")
    messages = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})
    messages.append({"role": "user", "content": user_input.strip()})
    return _call_chat_with_length_retry(model_id, messages, initial_max_tokens=2048, retry_max_tokens=4096)


def _image_from_value(value: Any) -> Image.Image:
    if isinstance(value, Image.Image):
        return value.copy()

    if isinstance(value, dict):
        for key in ("background", "composite", "image"):
            if value.get(key) is not None:
                return _image_from_value(value[key])

    if isinstance(value, str):
        if not value.startswith("data:image/") or "," not in value:
            raise ValueError("The img2img source image is missing or is not a supported data URL.")
        _, encoded = value.split(",", 1)
        return Image.open(io.BytesIO(base64.b64decode(encoded)))

    if hasattr(value, "shape"):
        return Image.fromarray(value)

    raise ValueError("Unsupported img2img image value.")


def _encode_image_data_url(value: Any, max_side: int = 1536) -> LMResult:
    try:
        image = ImageOps.exif_transpose(_image_from_value(value))
        if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
            rgba = image.convert("RGBA")
            flattened = Image.new("RGB", rgba.size, "white")
            flattened.paste(rgba, mask=rgba.getchannel("A"))
            image = flattened
        else:
            image = image.convert("RGB")

        if max(image.size) > max_side:
            resampling = getattr(Image, "Resampling", Image).LANCZOS
            image.thumbnail((max_side, max_side), resampling)

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return LMResult(text=f"data:image/jpeg;base64,{encoded}")
    except Exception as e:
        return LMResult(error=f"Failed to prepare the source image: {e}", kind="image")


def _call_lm_vision(
    user_input: str,
    system_prompt: str,
    image_value: Any,
    model_id: str,
) -> LMResult:
    encoded = _encode_image_data_url(image_value)
    if not encoded.ok:
        return encoded

    instruction = user_input.strip() or (
        "Describe the source image faithfully as a Stable Diffusion img2img prompt. "
        "Do not intentionally change its content."
    )
    vision_system = VISION_SYSTEM_PREFIX + (system_prompt.strip() or DEFAULT_PRESETS["Normal"])
    messages = [
        {"role": "system", "content": vision_system},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": instruction},
                {"type": "image_url", "image_url": {"url": encoded.text}},
            ],
        },
    ]
    return _call_chat_with_length_retry(
        model_id,
        messages,
        initial_max_tokens=2048,
        retry_max_tokens=4096,
        require_vision=True,
    )


def _parse_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return fallback
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _is_batch_job() -> bool:
    return bool(re.match(r"^\d+\s+out\s+of\s+\d+$", str(getattr(shared.state, "job", "") or "")))


# ── UI / Forge処理 ──────────────────────────────────────────────────────────
class LLMDecoratorScript(scripts.Script):

    create_group = False

    def __init__(self):
        self.on_after_component_elem_id = [
            ("txt2img_prompt_row", lambda c: self._build_ui(c, "txt2img")),
            ("img2img_prompt_row", lambda c: self._build_ui(c, "img2img")),
        ]
        # Batch内でDynamic Promptsが複数組み合わせを生成しても、
        # 同じ入力画像についてVision LLMを呼ぶのは1回だけにする。
        self._llmuse_batch_prompt_cache = {}
        self._llmuse_active_batch_run_id = None

    def title(self):
        return "LLMuse"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        if not is_img2img:
            return []

        settings = _load_settings()
        presets = _load_presets()
        initial = _initial_preset(settings, presets, "img2img")

        # Forgeのimg2img Generate時に process() へ渡すための非表示引数。
        # 画面上のLLMuse値はJavaScript側でGenerate直前に同期する。
        batch_enabled_arg = gr.Textbox(
            value="true" if settings.get("batch_vision_enabled") else "false",
            lines=1,
            show_label=False,
            interactive=True,
            elem_id="llm_dec_batch_enabled_arg_img2img",
            elem_classes="llm-dec-sp-hidden",
        )
        instruction_arg = gr.Textbox(
            value=settings.get("img2img_instruction", ""),
            lines=1,
            show_label=False,
            interactive=True,
            elem_id="llm_dec_instruction_arg_img2img",
            elem_classes="llm-dec-sp-hidden",
        )
        system_prompt_arg = gr.Textbox(
            value=presets.get(initial, ""),
            lines=1,
            show_label=False,
            interactive=True,
            elem_id="llm_dec_system_prompt_arg_img2img",
            elem_classes="llm-dec-sp-hidden",
        )
        vision_model_arg = gr.Textbox(
            value=settings.get("vision_model", ""),
            lines=1,
            show_label=False,
            interactive=True,
            elem_id="llm_dec_vision_model_arg_img2img",
            elem_classes="llm-dec-sp-hidden",
        )
        batch_run_id_arg = gr.Textbox(
            value="",
            lines=1,
            show_label=False,
            interactive=True,
            elem_id="llm_dec_batch_run_id_arg_img2img",
            elem_classes="llm-dec-sp-hidden",
        )
        return [
            batch_enabled_arg,
            instruction_arg,
            system_prompt_arg,
            vision_model_arg,
            batch_run_id_arg,
        ]

    def _get_batch_prompt_config(self, args):
        settings = _load_settings()
        batch_enabled = _parse_bool(
            args[0] if len(args) > 0 else None,
            bool(settings.get("batch_vision_enabled")),
        )
        if not batch_enabled:
            return None

        instruction = str(args[1] if len(args) > 1 else "").strip() or str(
            settings.get("img2img_instruction", "")
        ).strip()
        system_prompt = str(args[2] if len(args) > 2 else "").strip()
        vision_model = str(args[3] if len(args) > 3 else "").strip() or str(
            settings.get("vision_model", "")
        ).strip()
        batch_run_id = str(args[4] if len(args) > 4 else "").strip() or "legacy-batch-run"

        if not system_prompt:
            presets = _load_presets()
            initial = _initial_preset(settings, presets, "img2img")
            system_prompt = presets.get(initial, DEFAULT_PRESETS["Normal"])

        return instruction, system_prompt, vision_model, batch_run_id

    @staticmethod
    def _batch_image_digest(image: Any) -> str:
        """入力画像の内容から、Dynamic Promptsの組み合わせをまたいで安定するキーを作る。"""
        prepared = ImageOps.exif_transpose(_image_from_value(image)).convert("RGB")
        # ハッシュ計算負荷を抑えつつ、同一入力画像を確実に識別する。
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        prepared.thumbnail((512, 512), resampling)
        h = hashlib.blake2b(digest_size=16)
        h.update(str(prepared.size).encode("ascii"))
        h.update(prepared.mode.encode("ascii"))
        h.update(prepared.tobytes())
        return h.hexdigest()

    def _apply_batch_prompt(self, p, args, force_batch: bool = False, **kwargs):
        if not getattr(self, "is_img2img", False):
            return
        if not force_batch and not _is_batch_job():
            return

        config = self._get_batch_prompt_config(args)
        if not config:
            return
        instruction, system_prompt, vision_model, batch_run_id = config

        if self._llmuse_active_batch_run_id != batch_run_id:
            self._llmuse_batch_prompt_cache.clear()
            self._llmuse_active_batch_run_id = batch_run_id

        job = str(getattr(shared.state, "job", "batch image") or "batch image")
        image = p.init_images[0] if getattr(p, "init_images", None) else None
        if image is None:
            for key in ("images", "batch_images", "init_images"):
                value = kwargs.get(key)
                if value:
                    image = value[0]
                    break
        if image is None:
            return

        try:
            image_digest = self._batch_image_digest(image)
        except Exception as e:
            print(f"[LLMuse] {job}: failed to identify batch image: {e}")
            shared.state.skip()
            return

        cache_key = (
            batch_run_id,
            image_digest,
            instruction,
            system_prompt,
            vision_model,
        )
        result = self._llmuse_batch_prompt_cache.get(cache_key)

        if result is None:
            result = _call_lm_vision(instruction, system_prompt, image, vision_model)
            if not result.ok and result.kind == "empty":
                result = _call_lm_vision(instruction, system_prompt, image, vision_model)
            self._llmuse_batch_prompt_cache[cache_key] = result
            print(f"[LLMuse] {job}: analyzed source image once for batch run {batch_run_id}.")
        else:
            print(f"[LLMuse] {job}: reused cached prompt for Dynamic Prompts combination.")

        if result.ok:
            prompt_text = result.text
            p.prompt = prompt_text
            if hasattr(p, "main_prompt"):
                p.main_prompt = prompt_text
            if hasattr(p, "prompt_for_display"):
                p.prompt_for_display = prompt_text
            if hasattr(p, "all_prompts") and isinstance(getattr(p, "all_prompts", None), list):
                p.all_prompts = [prompt_text for _ in p.all_prompts] or [prompt_text]
            prompts = kwargs.get("prompts")
            if isinstance(prompts, list) and prompts:
                for i in range(len(prompts)):
                    prompts[i] = prompt_text
            if hasattr(p, "extra_generation_params") and isinstance(p.extra_generation_params, dict):
                p.extra_generation_params["LLMuse Batch"] = "On"
                p.extra_generation_params["LLMuse Prompt"] = prompt_text[:200]
            shared.state.textinfo = f"LLMuse batch prompt ready: {job}"
            print(f"[LLMuse] {job}: generated an img2img prompt with {vision_model}.")
            return

        if result.kind in {"image", "empty", "length"}:
            print(f"[LLMuse] {job}: skipped this image: {result.error}")
            shared.state.textinfo = f"LLMuse skipped {job}: {result.error}"
            shared.state.skip()
            return

        print(f"[LLMuse] Batch stopped at {job}: {result.error}")
        shared.state.textinfo = f"LLMuse batch stopped: {result.error}"
        shared.state.interrupt()

    def before_process_batch(self, p, *args, **kwargs):
        self._apply_batch_prompt(p, args, force_batch=True, **kwargs)

    def process_batch(self, p, *args, **kwargs):
        self._apply_batch_prompt(p, args, force_batch=True, **kwargs)

    def process_before_every_sampling(self, p, *args, **kwargs):
        self._apply_batch_prompt(p, args, force_batch=True, **kwargs)

    def process(self, p, *args):
        self._apply_batch_prompt(p, args, force_batch=False)

    def _build_ui(self, _component: OnComponent, tab: str):
        presets = _load_presets()
        names = list(presets.keys())
        settings = _load_settings()
        initial = _initial_preset(settings, presets, tab)

        model_choices = _get_models(vision_only=(tab == "img2img"))
        model_key = "vision_model" if tab == "img2img" else "model"
        model_value = settings.get(model_key) or None
        input_value = settings.get("img2img_instruction", "") if tab == "img2img" else ""
        input_placeholder = (
            "Describe how to change the source image…"
            if tab == "img2img"
            else "Enter instructions for the Stable Diffusion prompt…"
        )

        with gr.Accordion(
            "✦ LLMuse",
            open=False,
            elem_id=f"llm_dec_{tab}",
            elem_classes="llm-dec-root",
        ):
            with gr.Row():
                with gr.Column(scale=1):
                    with gr.Row():
                        preset_dropdown = gr.Dropdown(
                            choices=names,
                            value=initial,
                            show_label=False,
                            scale=5,
                            elem_id=f"llm_dec_dropdown_{tab}",
                        )
                        preset_btn = gr.Button("📋", scale=1, min_width=40)
                        settings_btn = gr.Button("⚙", scale=1, min_width=40)
                    user_input = gr.Textbox(
                        value=input_value,
                        lines=4,
                        show_label=False,
                        placeholder=input_placeholder,
                        elem_id=f"llm_dec_input_{tab}",
                    )
                    if tab == "img2img":
                        batch_vision = gr.Checkbox(
                            label="Analyze each batch image",
                            value=bool(settings.get("batch_vision_enabled")),
                            elem_id="llm_dec_batch_vision_img2img",
                        )
                    else:
                        batch_vision = None
                    run_btn = gr.Button(
                        "Run LLM",
                        variant="primary",
                        elem_id=f"llm_dec_run_btn_{tab}",
                    )

                with gr.Column(scale=1):
                    send_mode = settings.get("send_mode", "append")
                    with gr.Row():
                        model_dropdown = gr.Dropdown(
                            choices=model_choices,
                            value=model_value,
                            show_label=False,
                            elem_id=f"llm_dec_model_dropdown_{tab}",
                            allow_custom_value=True,
                            scale=5,
                        )
                        refresh_models_btn = gr.Button(
                            "↻",
                            scale=0,
                            min_width=40,
                            elem_id=f"llm_dec_refresh_models_{tab}",
                        )
                        send_mode_radio = gr.Radio(
                            choices=["Add", "Rep"],
                            value="Rep" if send_mode == "replace" else "Add",
                            show_label=False,
                            scale=0,
                        )
                    output = gr.Textbox(
                        lines=4,
                        show_label=False,
                        interactive=True,
                        elem_id=f"llm_dec_output_{tab}",
                    )
                    send_btn = gr.Button(
                        "Send",
                        variant="secondary",
                        elem_id=f"llm_dec_send_btn_{tab}",
                    )

            # ── 非表示コンポーネント: プリセット / 設定 / 画像 ──
            system_prompt = gr.Textbox(
                value=presets[initial],
                lines=1,
                show_label=False,
                interactive=True,
                elem_id=f"llm_dec_sp_{tab}",
                elem_classes="llm-dec-sp-hidden",
            )
            presets_json = gr.Textbox(
                value=json.dumps(presets, ensure_ascii=False),
                lines=1,
                show_label=False,
                interactive=False,
                elem_id=f"llm_dec_presets_json_{tab}",
                elem_classes="llm-dec-sp-hidden",
            )
            save_trigger = gr.Textbox(
                value="",
                lines=1,
                show_label=False,
                interactive=True,
                elem_id=f"llm_dec_save_trigger_{tab}",
                elem_classes="llm-dec-sp-hidden",
            )
            delete_trigger = gr.Textbox(
                value="",
                lines=1,
                show_label=False,
                interactive=True,
                elem_id=f"llm_dec_delete_trigger_{tab}",
                elem_classes="llm-dec-sp-hidden",
            )
            settings_json = gr.Textbox(
                value=json.dumps(settings, ensure_ascii=False),
                lines=1,
                show_label=False,
                interactive=False,
                elem_id=f"llm_dec_settings_json_{tab}",
                elem_classes="llm-dec-sp-hidden",
            )
            settings_trigger = gr.Textbox(
                value="",
                lines=1,
                show_label=False,
                interactive=True,
                elem_id=f"llm_dec_settings_trigger_{tab}",
                elem_classes="llm-dec-sp-hidden",
            )
            force_unload_trigger = gr.Textbox(
                value="",
                lines=1,
                show_label=False,
                interactive=True,
                elem_id=f"llm_dec_force_unload_trigger_{tab}",
                elem_classes="llm-dec-sp-hidden",
            )
            force_unload_status = gr.Textbox(
                value="",
                lines=1,
                show_label=False,
                interactive=False,
                elem_id=f"llm_dec_force_unload_status_{tab}",
                elem_classes="llm-dec-sp-hidden",
            )
            source_image_data = gr.Textbox(
                value="",
                lines=1,
                show_label=False,
                interactive=True,
                elem_id=f"llm_dec_source_image_{tab}",
                elem_classes="llm-dec-sp-hidden",
            )
            lm_result = gr.Textbox(
                value="",
                lines=1,
                show_label=False,
                interactive=False,
                elem_id=f"llm_dec_lm_result_{tab}",
                elem_classes="llm-dec-sp-hidden",
            )

            # ── イベント: ボタン / 設定 ──
            settings_btn.click(fn=None, _js=f"() => llmDecOpenSettings('{tab}')")
            preset_btn.click(fn=None, _js=f"() => llmDecOpenModal('{tab}')")

            def on_send_mode_change(value):
                mode = "replace" if value == "Rep" else "append"
                s = _save_settings({"send_mode": mode})
                return gr.update(value=json.dumps(s, ensure_ascii=False))

            send_mode_radio.change(
                fn=on_send_mode_change,
                inputs=[send_mode_radio],
                outputs=[settings_json],
            )

            def on_preset_change(name):
                _save_last_preset(name, tab)
                return _load_presets().get(name, "")

            preset_dropdown.change(
                fn=on_preset_change,
                inputs=[preset_dropdown],
                outputs=[system_prompt],
            )

            def on_save_trigger(cmd):
                if not cmd:
                    return gr.update(), gr.update(), gr.update()
                try:
                    data = json.loads(cmd)
                    name = data.get("name", "").strip()
                    content = data.get("content", "")
                except Exception:
                    return gr.update(), gr.update(), gr.update()
                if not name:
                    return gr.update(), gr.update(), gr.update()
                p = _load_presets()
                p[name] = content
                _save_presets(p)
                _save_last_preset(name, tab)
                return (
                    gr.update(choices=list(p.keys()), value=name),
                    gr.update(value=json.dumps(p, ensure_ascii=False)),
                    gr.update(value=content),
                )

            save_trigger.change(
                fn=on_save_trigger,
                inputs=[save_trigger],
                outputs=[preset_dropdown, presets_json, system_prompt],
            )

            def on_delete_trigger(cmd):
                if not cmd:
                    return gr.update(), gr.update(), gr.update()
                try:
                    name = json.loads(cmd).get("name", "").strip()
                except Exception:
                    return gr.update(), gr.update(), gr.update()
                p = _load_presets()
                if not name or name not in p or len(p) <= 1:
                    return gr.update(), gr.update(), gr.update()
                p.pop(name)
                _save_presets(p)
                ns = list(p.keys())
                _save_last_preset(ns[0], tab)
                return (
                    gr.update(choices=ns, value=ns[0]),
                    gr.update(value=json.dumps(p, ensure_ascii=False)),
                    gr.update(value=p.get(ns[0], "")),
                )

            delete_trigger.change(
                fn=on_delete_trigger,
                inputs=[delete_trigger],
                outputs=[preset_dropdown, presets_json, system_prompt],
            )

            def on_settings_trigger(cmd):
                if not cmd:
                    return gr.update()
                try:
                    s = _save_settings(json.loads(cmd))
                    return gr.update(value=json.dumps(s, ensure_ascii=False))
                except Exception:
                    return gr.update()

            settings_trigger.change(
                fn=on_settings_trigger,
                inputs=[settings_trigger],
                outputs=[settings_json],
            )

            def on_force_unload_trigger(_):
                try:
                    base = _load_settings().get("lm_url", LM_STUDIO_BASE)
                    _unload_all_models(base)
                    return "✓"
                except Exception as e:
                    return f"✕ {e}"

            force_unload_trigger.change(
                fn=on_force_unload_trigger,
                inputs=[force_unload_trigger],
                outputs=[force_unload_status],
            )

            def on_model_dropdown_change(model_id):
                s = _save_settings({model_key: model_id or ""})
                return gr.update(value=json.dumps(s, ensure_ascii=False))

            model_dropdown.change(
                fn=on_model_dropdown_change,
                inputs=[model_dropdown],
                outputs=[settings_json],
            )

            def on_refresh_models(current_model):
                choices = _get_models(vision_only=(tab == "img2img"))
                value = current_model or None
                return gr.update(choices=choices, value=value)

            refresh_models_btn.click(
                fn=on_refresh_models,
                inputs=[model_dropdown],
                outputs=[model_dropdown],
            )

            if tab == "img2img":
                def on_instruction_change(value):
                    s = _save_settings({"img2img_instruction": value or ""})
                    return gr.update(value=json.dumps(s, ensure_ascii=False))

                user_input.change(
                    fn=on_instruction_change,
                    inputs=[user_input],
                    outputs=[settings_json],
                )

                def on_batch_vision_change(value):
                    s = _save_settings({"batch_vision_enabled": bool(value)})
                    return gr.update(value=json.dumps(s, ensure_ascii=False))

                batch_vision.change(
                    fn=on_batch_vision_change,
                    inputs=[batch_vision],
                    outputs=[settings_json],
                )

            def _call_lm_ui(user_text: str, preset_text: str, image_data: str):
                s = _load_settings()
                if tab == "img2img":
                    if image_data == "__LLMUSE_BATCH_MODE__":
                        # Batch画像はForge側がGenerate開始後に順番に渡すため、
                        # JavaScriptへBatch開始指示だけ返し、各画像の解析はprocess()で行う。
                        return gr.update(value=""), "__LLMUSE_START_BATCH__"
                    elif image_data == "__LLMUSE_UNSUPPORTED_IMG2IMG_MODE__":
                        result = LMResult(
                            error="This first version supports the standard img2img tab and Batch tab only.",
                            kind="fatal",
                        )
                    elif not image_data:
                        result = LMResult(
                            error="Load a source image in the standard img2img tab first.",
                            kind="image",
                        )
                    else:
                        result = _call_lm_vision(
                            user_text,
                            preset_text,
                            image_data,
                            str(s.get("vision_model", "")),
                        )
                else:
                    result = _call_lm_text(
                        user_text,
                        preset_text,
                        str(s.get("model", "")),
                    )

                should_auto_send = (
                    s.get("auto_send")
                    or s.get("auto_generate")
                    or s.get("continuous_generate")
                )
                if result.ok and should_auto_send:
                    return gr.update(value=""), result.text
                if result.ok:
                    return result.text, ""
                return f"Error: {result.error}", ""

            run_btn.click(
                fn=_call_lm_ui,
                inputs=[user_input, system_prompt, source_image_data],
                outputs=[output, lm_result],
                _js=f"(u, s, img) => llmDecPrepareRunInputs(u, s, img, '{tab}')",
            ).then(
                fn=None,
                inputs=[lm_result],
                outputs=[],
                _js=f"(t) => llmDecAutoSend(t, '{tab}')",
            )
            send_btn.click(
                fn=None,
                inputs=[output],
                outputs=[],
                _js=f"(t) => llmDecManualSend(t, '{tab}')",
            )
