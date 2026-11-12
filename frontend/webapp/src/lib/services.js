import SpotifyLogo from '@/assets/media/Spotify-mine.svg?react'
import YoutubeLogo from '@/assets/media/Yt-mine.svg?react'
import AppleMusicLogo from '@/assets/media/apple_music-mine.svg?react'
import NetflixLogo from '@/assets/media/netflix-mine.svg?react'
import ClaudeLogo from '@/assets/media/claude-mine.svg?react'
import ChatgptLogo from '@/assets/media/chatgpt-mine.svg?react'
import CursorLogo from '@/assets/media/cursor-mine.svg?react'
import GoogleLogo from '@/assets/media/google-1-mine.svg?react'
import PrimeLogo from '@/assets/media/amazon-prime-mine.svg?react'
import HotstarLogo from '@/assets/media/hotstar-mine.svg?react'
import CanvaLogo from '@/assets/media/canva-mine.svg?react'

/** Natural sizes from each file's viewBox. The files have no width or height. */
export const SVG_SIZES = {
  logo: { w: 175.13, h: 168.13 },
  wordmark: { w: 167.06, h: 42.58 },
  hero: { w: 1440, h: 760 },
  chat: { w: 327.89, h: 607.37 },
  footer: { w: 1440, h: 710.35 },
}

/** Preset service key → logo and brand color. Adding a logo is one line here. */
export const SERVICES = {
  spotify: { name: 'Spotify', Logo: SpotifyLogo, color: '#1db954' },
  youtube: { name: 'YouTube', Logo: YoutubeLogo, color: '#ff0033' },
  apple_music: { name: 'Apple Music', Logo: AppleMusicLogo, color: '#000000' },
  netflix: { name: 'Netflix', Logo: NetflixLogo, color: '#ff0013' },
  claude: { name: 'Claude', Logo: ClaudeLogo, color: '#d97757' },
  chatgpt: { name: 'ChatGPT', Logo: ChatgptLogo, color: '#10a37f' },
  cursor: { name: 'Cursor', Logo: CursorLogo, color: '#1a1a1a' },
  google: { name: 'Google One', Logo: GoogleLogo, color: '#4285f4' },
  prime: {
    name: 'Amazon Prime Video',
    aliases: ['Amazon Prime'],
    Logo: PrimeLogo,
    color: '#00a8e1',
  },
  hotstar: { name: 'Disney+ Hotstar', Logo: HotstarLogo, color: '#1f3fbf' },
  canva: { name: 'Canva', Logo: CanvaLogo, color: '#1e88e5' },
}

export function serviceInfo(key) {
  return SERVICES[key] ?? null
}

/** Map catalog / API service name to preset `serviceKey` (logo + color). */
export function lookupServiceKey(name) {
  const raw = String(name ?? '').trim().toLowerCase()
  if (!raw) return null
  for (const [key, spec] of Object.entries(SERVICES)) {
    const labels = [spec.name, ...(spec.aliases ?? [])].map((n) => n.toLowerCase())
    if (labels.includes(raw)) return key
  }
  if (raw.includes('amazon prime')) return 'prime'
  return null
}
