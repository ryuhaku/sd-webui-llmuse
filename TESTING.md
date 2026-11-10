# LLMuse img2img / Batch test checklist

## Implemented scope

- LLMuse UI is shown in both txt2img and img2img.
- The model selector is labeled `Text model` or `Vision model` and has a refresh button.
- A selected but unloaded model is loaded through LM Studio automatically.
- Standard img2img sends the source image and LLMuse instruction to a Vision model.
- Add / Rep and Auto-generate work in standard img2img.
- `Analyze each batch image` generates a separate replacement prompt for each image in Forge Neo's Batch tab.
- Batch input supports both uploaded files and input directories through Forge Neo's existing batch processing.
- System/model/API errors interrupt the batch.
- Image conversion failures and repeated empty VLM responses skip only the affected image.
- Continuous right-click is ignored before Continuous starts. During generation it stops after the current image; during the inter-image delay it stops immediately.

## Deliberately not implemented in this version

- Sketch, Inpaint, Inpaint sketch, or Inpaint upload analysis.
- Feeding generated images back into the next img2img cycle.
- Continuous control over an entire Forge Batch job.

## Suggested test order

1. Start the LM Studio server, but leave the selected Vision model unloaded.
2. Restart Forge Neo and open img2img.
3. In LLMuse, select a Vision model. Use the refresh button if the list is empty.
4. Load one image in the standard `img2img` tab, enter an instruction, and press `Run LLM`.
5. Confirm that LM Studio automatically loads the selected model and LLMuse outputs an image-aware prompt.
6. Test Add and Rep separately.
7. Enable Auto-generate and confirm that a successful prompt starts img2img generation.
8. Open Batch, select/upload several images, enable `Analyze each batch image`, and press Forge Neo's Generate button.
9. Confirm in the console that each image gets a separate `[LLMuse] n out of N` prompt message.
10. Stop LM Studio or select a non-Vision model and confirm that the batch stops rather than continuing with the original prompt.
11. Before starting Continuous, right-click Run LLM and confirm that nothing changes. Then start Continuous and verify the stop behavior.

## Validation already performed

- Python syntax compilation.
- JavaScript syntax check with Node.js.
- PIL image conversion and Base64/JPEG generation.
- Mock LM Studio model-list, model-load, and image chat-completion requests.
- Batch success, fatal interruption, and image-specific skip branches with Forge state stubs.

Actual Forge Neo UI and end-to-end generation still require local testing because the Forge runtime and LM Studio models are not available in the build environment.

## Strata provider (feature/strata-provider)

### Implemented scope

- Settings → `LLM Provider` selects `LM Studio` or `Strata`; the choice and both URLs are persisted.
- A missing `provider` in an existing `settings.json` keeps LM Studio behaviour (backward compatible).
- Model lists are read per provider: LM Studio `GET /api/v1/models`, Strata `GET /v1/models` (`data[].id`).
- Model selection is stored per provider (`model`/`vision_model` for LM Studio, `strata_model`/`strata_vision_model` for Strata), so LM Studio model IDs are never sent to Strata.
- Strata requests add `Authorization: Bearer` only when `LLMUSE_STRATA_API_KEY` (or `STRATA_API_KEY`) exists in the environment; the key never enters settings.json, the UI state JSON, or error text.
- Strata requests use `reasoning_effort: "none"` and never send `enable_thinking`, `ttl`, or any model load/unload request.
- Auto-unload and Force Unload are hidden while Strata is selected, and Force Unload issues no request in Strata mode.
- Connection, authentication, model-list failure, empty list, empty response and timeout are distinguished and labelled with the active provider; a failed Run LLM never sends a prompt or starts image generation.

### Automated checks performed

`llmuse_strata_test.py` (workspace) — 35 checks, all passing, with a mock LM Studio/Strata server plus one live Strata instance: settings backward compatibility, per-provider model list and auto-selection, absence of model-management requests in Strata mode, 401/connection/empty handling, API key masking, unchanged LM Studio parameters and wording, and one live Japanese → English prompt generation.

`llmuse_ui_build_test.py` (workspace) — builds the real Gradio UI for both tabs in three states (Strata reachable, Strata down, LM Studio down) without starting the WebUI.

### Not verified in the build environment

- The real Forge Neo UI: the provider switch in the settings dialog, Add/Rep, Auto-send, Auto-generate, Continuous and its right-click stop.
- A live LM Studio server (it was not running); LM Studio behaviour was checked only against a mock.
- Strata img2img/Vision prompts.

### Suggested manual test order

1. Start Strata and check its current API port (Strata assigns a new port on each start unless it is fixed in Strata itself).
2. Start Forge Neo, open LLMuse → ⚙ Settings → `LLM Provider` = `Strata`, set `Strata URL` to the current port (base URL only, without `/v1`), then Save.
3. Confirm the model dropdown lists the Strata model and that the Auto-unload/Force Unload rows are gone.
4. Enter a Japanese instruction, press Run LLM, and confirm an English prompt with no reasoning text.
5. Test Add/Rep, Auto-send, Auto-generate, then Continuous, and stop it with a right-click.
6. Stop Strata (or set a wrong URL) and confirm the error is shown, no prompt is sent, and Continuous stops.
7. Switch back to `LM Studio` and confirm the previous model list, auto-load and VRAM behaviour still work.
8. If an API key is enabled in Strata, set `LLMUSE_STRATA_API_KEY` before starting Forge Neo; the 401 message names that variable.
