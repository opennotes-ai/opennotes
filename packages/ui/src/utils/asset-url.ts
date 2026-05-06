const ASSET_BASE = "https://storage.googleapis.com/open-notes-core-public-assets";

export function getAssetUrl(name: string): string {
  return `${ASSET_BASE}/${name}`;
}
