import SpotifyLogo from '@/assets/media/Spotify-mine.svg?react'
import YoutubeLogo from '@/assets/media/Yt-mine.svg?react'
import YoutubeMusicLogo from '@/assets/media/yt-music.svg?react'
import AppleMusicLogo from '@/assets/media/apple_music-mine.svg?react'
import NetflixLogo from '@/assets/media/netflix-mine.svg?react'
import ClaudeLogo from '@/assets/media/claude-mine.svg?react'
import ChatgptLogo from '@/assets/media/chatgpt-mine.svg?react'
import CursorLogo from '@/assets/media/cursor-mine.svg?react'
import GoogleLogo from '@/assets/media/google-1-mine.svg?react'
import PrimeLogo from '@/assets/media/amazon-prime-mine.svg?react'
import HotstarLogo from '@/assets/media/hotstar-mine.svg?react'
import CanvaLogo from '@/assets/media/canva-mine.svg?react'
import HoichoiLogo from '@/assets/media/hoichoi.svg?react'
import ChorkiLogo from '@/assets/media/chorki.svg?react'
import BongoLogo from '@/assets/media/bongo.svg?react'
import GeminiLogo from '@/assets/media/gemini.svg?react'
import MidjourneyLogo from '@/assets/media/midjourney.svg?react'
import GithubCopilotLogo from '@/assets/media/github-copilot.svg?react'
import Ms365Logo from '@/assets/media/ms-365.svg?react'
import AdobeLogo from '@/assets/media/adobe-creative-cloud.svg?react'
import NotionLogo from '@/assets/media/notion.svg?react'
import FigmaLogo from '@/assets/media/figma.svg?react'
import IcloudLogo from '@/assets/media/icloud+.svg?react'
import VercelLogo from '@/assets/media/vercel.svg?react'
import RenderLogo from '@/assets/media/render.svg?react'
import DigitaloceanLogo from '@/assets/media/digitalocean.svg?react'
import NamecheapLogo from '@/assets/media/namecheap.svg?react'
import GodaddyLogo from '@/assets/media/godaddy.svg?react'
import CloudflareLogo from '@/assets/media/cloudflare.svg?react'
import HomeBroadbandLogo from '@/assets/media/home-broadband.svg?react'
import MobileDataLogo from '@/assets/media/mobile-data.svg?react'
import ElectricityLogo from '@/assets/media/electricity.svg?react'
import GasLogo from '@/assets/media/gas.svg?react'
import WaterLogo from '@/assets/media/water.svg?react'

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
  youtube: {
    name: 'YouTube',
    aliases: ['YouTube Premium'],
    Logo: YoutubeLogo,
    color: '#ff0033',
  },
  youtube_music: { name: 'YouTube Music', Logo: YoutubeMusicLogo, color: '#ff0000' },
  apple_music: { name: 'Apple Music', Logo: AppleMusicLogo, color: '#000000' },
  netflix: { name: 'Netflix', Logo: NetflixLogo, color: '#ff0013' },
  hoichoi: { name: 'Hoichoi', Logo: HoichoiLogo, color: '#e50914' },
  chorki: { name: 'Chorki', Logo: ChorkiLogo, color: '#ff4d00' },
  bongo: { name: 'Bongo', Logo: BongoLogo, color: '#e30b5d' },
  claude: { name: 'Claude', Logo: ClaudeLogo, color: '#d97757' },
  chatgpt: { name: 'ChatGPT', Logo: ChatgptLogo, color: '#10a37f' },
  gemini: { name: 'Gemini', Logo: GeminiLogo, color: '#4285f4' },
  midjourney: { name: 'Midjourney', Logo: MidjourneyLogo, color: '#000000' },
  github_copilot: { name: 'GitHub Copilot', Logo: GithubCopilotLogo, color: '#000000' },
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
  microsoft_365: { name: 'Microsoft 365', Logo: Ms365Logo, color: '#d83b01' },
  adobe_creative_cloud: { name: 'Adobe Creative Cloud', Logo: AdobeLogo, color: '#ff0000' },
  notion: { name: 'Notion', Logo: NotionLogo, color: '#000000' },
  figma: { name: 'Figma', Logo: FigmaLogo, color: '#f24e1e' },
  icloud: { name: 'iCloud+', Logo: IcloudLogo, color: '#3693f3' },
  vercel: { name: 'Vercel', Logo: VercelLogo, color: '#000000' },
  render: { name: 'Render', Logo: RenderLogo, color: '#000000' },
  digitalocean: { name: 'DigitalOcean', Logo: DigitaloceanLogo, color: '#0080ff' },
  namecheap: { name: 'Namecheap (domains)', aliases: ['Namecheap'], Logo: NamecheapLogo, color: '#de3723' },
  godaddy: { name: 'GoDaddy (domains)', aliases: ['GoDaddy'], Logo: GodaddyLogo, color: '#1bdbdb' },
  cloudflare: { name: 'Cloudflare', Logo: CloudflareLogo, color: '#f38020' },
  home_broadband: { name: 'Home broadband', Logo: HomeBroadbandLogo, color: '#06b6d4' },
  mobile_data: { name: 'Mobile data pack', aliases: ['Mobile data'], Logo: MobileDataLogo, color: '#8b5cf6' },
  electricity: { name: 'Electricity', Logo: ElectricityLogo, color: '#facc15' },
  gas: { name: 'Gas', Logo: GasLogo, color: '#f97316' },
  water: { name: 'Water', Logo: WaterLogo, color: '#3b82f6' },
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
  if (raw.includes('disney') || raw.includes('hotstar')) return 'hotstar'
  if (raw.includes('youtube music')) return 'youtube_music'
  if (raw.includes('youtube')) return 'youtube'
  if (raw.includes('github copilot')) return 'github_copilot'
  if (raw.includes('microsoft 365') || raw.includes('office 365')) return 'microsoft_365'
  if (raw.includes('adobe creative')) return 'adobe_creative_cloud'
  if (raw.includes('icloud')) return 'icloud'
  if (raw.includes('namecheap')) return 'namecheap'
  if (raw.includes('godaddy')) return 'godaddy'
  if (raw.includes('mobile data')) return 'mobile_data'
  if (raw.includes('broadband')) return 'home_broadband'
  return null
}