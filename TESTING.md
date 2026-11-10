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
