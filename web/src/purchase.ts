const GITHUB_HOSTS = new Set(["github.com", "raw.githubusercontent.com"]);

function parseUrl(url: string): URL | null {
  try {
    return new URL(url);
  } catch {
    return null;
  }
}

/** True when the URL points at a GitHub-hosted filaments_color_codes table rather than a store page. */
export function isGithubColorTableUrl(url: string): boolean {
  const parsed = parseUrl(url.trim());
  if (parsed === null) return false;
  return (
    GITHUB_HOSTS.has(parsed.hostname.toLowerCase()) &&
    parsed.pathname.toLowerCase().includes("filaments_color_codes")
  );
}

/** Clickable purchase URL, or null when empty, unparseable, or a GitHub color table. */
export function purchaseHref(url: string): string | null {
  if (url.trim() === "") return null;
  if (parseUrl(url.trim()) === null) return null;
  if (isGithubColorTableUrl(url)) return null;
  return url;
}
