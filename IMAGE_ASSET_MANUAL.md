# Civilization Image Asset Manual

Image Lab is intentionally focused on two asset jobs:

1. Generate NovelAI-style prompt packages for unit themes, diplomacy backgrounds, and moment pictures.
2. Create quick OpenAI image drafts for Civilization icons only.

## Asset Types

Use the **Image Lab** page and choose one asset type:

- **Civilization Icon**: OpenAI prompt and image generation for square emblems, crests, symbols, or readable faction marks.
- **Unit Theme**: NovelAI prompt preset for readable Civ-style unit concepts, equipment, faction colors, and icon-crop friendly silhouettes.
- **Diplomacy Background**: NovelAI prompt preset for wide `1920x960` diplomatic scenes, throne rooms, landscapes, or civ atmosphere images.
- **Moment Picture**: NovelAI prompt preset for square scene art that crops into `375x375` moment images.

ARX is handled by the Cropper page with the **ARX Icons** profile, which produces `54x54` files.

Keep the subject simple enough to survive icon resizing. Text, tiny heraldry, and heavy background detail usually collapse when the cropper makes small sizes.

## Prompt Fields

Fill in:

- **Subject**: exact civilization symbol, faction name, artifact, or crest idea.
- **Civilization / theme**: culture, palette, historical flavor, materials, motifs.
- **Visual brief**: composition, icon readability, unit equipment, diplomacy environment, object angle, lighting, background simplicity.
- **Extra style tags**: rendering style, material finish, decoration level.
- **Avoid**: clutter, text, logos, watermarks, bad perspective, fuzzy edges.
- **Must include**: mandatory symbol, color, shape, or crop requirement.

The tool returns:

- NovelAI positive prompt.
- NovelAI undesired content.
- Suggested settings: resolution, sampler, steps, prompt guidance, seed.
- An OpenAI image prompt for Civ icon drafts when the selected asset type supports OpenAI creation.

## NovelAI Settings Guidance

Start with the generated settings. For best cropper results:

- Use square generation for NovelAI moment pictures and unit concepts when you want easy later cropping.
- Keep the main shape, unit silhouette, or scene action centered and readable.
- Avoid text because it will usually distort or become unreadable.
- Prefer simple backgrounds; the cropper can remove them more cleanly.
- Ask for strong edge definition and high contrast between subject and background.
- For Unit Theme, describe weapon, armor, stance, faction color accents, and a pose that still works after cropping.
- For Diplomacy Background, keep the scene wide at `1920x960`, avoid portrait closeups, and leave useful negative space for game UI.
- For Moment Picture, keep the important action centered so the cropper can make a clean `375x375` square.

## OpenAI Image Creator

The OpenAI Image Creator calls the OpenAI Images API from the backend using your `.env` API key. It is limited to Civilization Icon drafts. Unit Theme, Diplomacy Background, and Moment Picture are NovelAI-only.

Recommended starting values:

- Model: `gpt-image-2`
- Size: `1024x1024`
- Quality: `auto` or `medium`
- Background: `auto`; use `transparent` for isolated emblem drafts when supported
- Format: `png`

After generation, feed the image into the Cropper page:

- Use **Civilization Icons** for Civ emblems and faction symbols.
- Use **ARX Icons** for `54x54` ARX output.
- Use **Diplomacy Backgrounds** to HD-upscale and cover-fit ordinary background art into `1920x960` diploBG files.
- Use **Moment Pictures** to HD-upscale and cover-fit scene art into `375x375` moment files.
- Use **Thumbnail 512** to HD-upscale and cover-fit preview art into `512x512` thumbnail files.
- Use **Raw 256** when you only need a clean 256x256 uploaded/raw icon.
- Use **Remove Background** before icon cropping when the generated background is too busy.
