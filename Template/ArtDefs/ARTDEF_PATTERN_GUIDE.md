# Civ VI ArtDef Pattern Notes

This is the short version for using the ArtDef templates without reading the giant files line by line.

## Where ArtDefs Are Registered

`Civ6.Art.xml` is the art registry. It groups art files by `consumerName`.

The useful pattern is:

```xml
<Element>
  <consumerName text="Landmarks"/>
  <relativeArtDefPaths>
    <Element text="Civilizations.artdef"/>
    <Element text="Improvements.artdef"/>
  </relativeArtDefPaths>
  <libraryDependencies>
    <Element text="CityBuildings"/>
    <Element text="TileBase"/>
  </libraryDependencies>
  <loadsLibraries>true</loadsLibraries>
</Element>
```

Add your `.artdef` file to the consumer that already loads the same asset family:

- Units: `Units`
- Civilizations / cultures / improvements: `Landmarks` and sometimes `Civilizations`
- Buildings / districts: `DistrictBuildings`
- Leaders: `Leaders` or `FallbackLeaders`
- UI/icon references: `UI` or `IconReferences`

Do not invent a new consumer unless you know the game expects it.

## ArtDef File Shape

The common `.artdef` shape is:

```xml
<AssetObjects..ArtDefSet>
  <m_TemplateName text="Civilizations"/>
  <m_RootCollections>
    <Element>
      <m_CollectionName text="Civilization"/>
      <Element>
        <m_Name text="CIVILIZATION_EXAMPLE"/>
        <m_Fields>...</m_Fields>
        <m_ChildCollections>...</m_ChildCollections>
      </Element>
    </Element>
  </m_RootCollections>
</AssetObjects..ArtDefSet>
```

The two parts you spam are usually:

- `m_Name`: the exact game ID, such as `UNIT_EXAMPLE` or `BUILDING_EXAMPLE`.
- Child collection entries: references to model assets, BLP/XLP texture entries, audio, strategic view, or fallback images.

## Practical Rules

- Copy the closest vanilla entry and replace IDs first.
- Keep `m_TemplateName`, `m_CollectionName`, `m_ParamName`, and reference collection names unchanged unless the vanilla example clearly differs.
- For leader fallback portraits, the reusable pattern is in `FallbackLeaders.artdef`: each leader points to `LeaderFallbackImages.xlp`, package `LeaderFallbackImages`, library `LeaderFallback`.
- For civilization entries, `Civilizations.artdef` mostly maps civilization IDs to an `Audio` child entry.
- For units/buildings, the files are much bigger because they include member models, strategic view, audio, cultures, eras, and attachments.

## Safe Template Copilot Use

Select only the ArtDef file family you are touching. Use Manual replacements JSON for exact IDs:

```json
{
  "TEMPLATE_ARTDEF_ID": "UNIT_NORTHBRIDGE_GUARD",
  "TEMPLATE_ASSET_NAME": "Northbridge_Guard"
}
```

Let OpenAI plan scalar replacements only. Do not ask it to rewrite whole ArtDef blocks.
