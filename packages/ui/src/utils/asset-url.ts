const ASSET_BASE = "https://storage.googleapis.com/open-notes-core-public-assets";

export type AssetName = "opennotes-logo.svg" | "favicon.ico" | "og-default.png";

export function getAssetUrl(name: AssetName): string {
  return `${ASSET_BASE}/${name}`;
}
