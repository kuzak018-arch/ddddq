/**
 * Dota's own interface icons in place of a generic icon set: the same names the code used from
 * lucide-react (Search, X, Trophy…), each drawing a white Dota icon (public/dota-icons/ui, from the
 * game's panorama files: control icons of the menu and the HUD, facet glyphs) as a mask in the text
 * colour. `size` works as it did; inside `.ti` the CSS sets it.
 */
import type { ComponentType, CSSProperties } from 'react';

export interface GlyphProps {
  size?: number | string;
  className?: string;
  style?: CSSProperties;
  title?: string;
  strokeWidth?: number; // accepted for the old call sites, has no effect
  'aria-hidden'?: boolean | 'true' | 'false';
}
export type LucideIcon = ComponentType<GlyphProps> & { displayName?: string };

const FILES: Record<string, string> = {
  Activity: 'graph.webp',
  AppWindow: 'full_screen.svg',
  ArrowLeft: 'arrow_left.svg',
  ArrowRight: 'arrow_right.svg',
  Ban: 'f_no_facet.webp',
  BookOpen: 'toc.webp',
  CalendarDays: 'clock.webp',
  ChartColumnIncreasing: 'stats.webp',
  ChartLine: 'graph.webp',
  Check: 'check.svg',
  ChevronsUp: 'arrow_up.svg',
  CircleUser: 'profile.svg',
  Clock: 'clock.webp',
  Coins: 'f_gold.webp',
  Crosshair: 'skull.svg',
  Crown: 'crown.webp',
  Database: 'folder.webp',
  Download: 'arrow_down.svg',
  Droplet: 'f_mana.webp',
  ExternalLink: 'popout.webp',
  FileArchive: 'folder.webp',
  Flag: 'flag.svg',
  Flame: 'f_dragon_fire.webp',
  Flower2: 'f_healing.webp',
  FolderOpen: 'folder.webp',
  Footprints: 'f_speed.webp',
  Gamepad2: 'hero.webp',
  Gem: 'f_rune.webp',
  GitFork: 'swap.webp',
  Globe: 'globe.svg',
  Hammer: 'hammer.svg',
  HeartHandshake: 'f_twin_hearts.webp',
  Hexagon: 'complexity.svg',
  House: 'home.svg',
  Image: 'picture.svg',
  Info: 'info.svg',
  KeyRound: 'lock.webp',
  Layers: 'layers.svg',
  LayoutGrid: 'grid.webp',
  Lightbulb: 'help.svg',
  ListOrdered: 'list.webp',
  MessageSquareText: 'message.svg',
  Monitor: 'display.svg',
  Moon: 'f_moon.webp',
  Move: 'move.webp',
  Package: 'f_item.webp',
  Paintbrush: 'f_brush.webp',
  Palette: 'f_brush.webp',
  Percent: 'f_pie.webp',
  Plug: 'ping.webp',
  RefreshCw: 'refresh.svg',
  RotateCcw: 'undo.svg',
  RotateCw: 'reset.svg',
  Route: 'f_movement.webp',
  ScanEye: 'eye.webp',
  ScrollText: 'toc.webp',
  Search: 'search.svg',
  Settings: 'settings.svg',
  Shapes: 'complexity.svg',
  Shield: 'hero.webp',
  ShieldBan: 'f_armor_broken.webp',
  ShoppingBag: 'secret_shop.svg',
  Shuffle: 'shuffle.webp',
  Skull: 'skull.svg',
  Sparkles: 'f_unique.webp',
  Star: 'star.webp',
  Store: 'secret_shop.svg',
  Sun: 'f_sun.webp',
  Sunrise: 'f_sun.webp',
  Swords: 'f_damage.webp',
  Table2: 'list.webp',
  Tag: 'flag.svg',
  Target: 'f_focus_fire.webp',
  ThumbsDown: 'thumbs_down.webp',
  Trash2: 'trash.svg',
  TrendingDown: 'graph.webp',
  TrendingUp: 'graph.webp',
  TriangleAlert: 'warning.svg',
  Trophy: 'cup.webp',
  Type: 'pencil.webp',
  Upload: 'arrow_up.svg',
  User: 'profile.svg',
  UserSearch: 'search.svg',
  Users: 'friends.webp',
  Volume2: 'volume.svg',
  Wand: 'unusual.svg',
  X: 'close.svg',
  Zap: 'f_rune.webp',
};

// absolute: a url() inside a CSS variable resolves against the stylesheet that uses it, not the page
export const glyphUrl = (file: string) => new URL(`${import.meta.env.BASE_URL}dota-icons/ui/${file}`, document.baseURI).href;

function make(name: string, file: string): LucideIcon {
  const G = ({ size, className = '', style, title, 'aria-hidden': hidden }: GlyphProps) => (
    <span
      className={`glyph ${className}`}
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : (hidden ?? true)}
      title={title}
      style={{ '--ico': `url("${glyphUrl(file)}")`, ...(size != null ? { '--gs': typeof size === 'number' ? `${size}px` : size } : {}), ...style } as CSSProperties}
    />
  );
  G.displayName = name;
  return G;
}

const g = (name: keyof typeof FILES) => make(name, FILES[name]!);

export const Activity = g('Activity');
export const AppWindow = g('AppWindow');
export const ArrowLeft = g('ArrowLeft');
export const ArrowRight = g('ArrowRight');
export const Ban = g('Ban');
export const BookOpen = g('BookOpen');
export const CalendarDays = g('CalendarDays');
export const ChartColumnIncreasing = g('ChartColumnIncreasing');
export const ChartLine = g('ChartLine');
export const Check = g('Check');
export const ChevronsUp = g('ChevronsUp');
export const CircleUser = g('CircleUser');
export const Clock = g('Clock');
export const Coins = g('Coins');
export const Crosshair = g('Crosshair');
export const Crown = g('Crown');
export const Database = g('Database');
export const Download = g('Download');
export const Droplet = g('Droplet');
export const ExternalLink = g('ExternalLink');
export const FileArchive = g('FileArchive');
export const Flag = g('Flag');
export const Flame = g('Flame');
export const Flower2 = g('Flower2');
export const FolderOpen = g('FolderOpen');
export const Footprints = g('Footprints');
export const Gamepad2 = g('Gamepad2');
export const Gem = g('Gem');
export const GitFork = g('GitFork');
export const Globe = g('Globe');
export const Hammer = g('Hammer');
export const HeartHandshake = g('HeartHandshake');
export const Hexagon = g('Hexagon');
export const House = g('House');
export const Image = g('Image');
export const Info = g('Info');
export const KeyRound = g('KeyRound');
export const Layers = g('Layers');
export const LayoutGrid = g('LayoutGrid');
export const Lightbulb = g('Lightbulb');
export const ListOrdered = g('ListOrdered');
export const MessageSquareText = g('MessageSquareText');
export const Monitor = g('Monitor');
export const Moon = g('Moon');
export const Move = g('Move');
export const Package = g('Package');
export const Paintbrush = g('Paintbrush');
export const Palette = g('Palette');
export const Percent = g('Percent');
export const Plug = g('Plug');
export const RefreshCw = g('RefreshCw');
export const RotateCcw = g('RotateCcw');
export const RotateCw = g('RotateCw');
export const Route = g('Route');
export const ScanEye = g('ScanEye');
export const ScrollText = g('ScrollText');
export const Search = g('Search');
export const Settings = g('Settings');
export const Shapes = g('Shapes');
export const Shield = g('Shield');
export const ShieldBan = g('ShieldBan');
export const ShoppingBag = g('ShoppingBag');
export const Shuffle = g('Shuffle');
export const Skull = g('Skull');
export const Sparkles = g('Sparkles');
export const Star = g('Star');
export const Store = g('Store');
export const Sun = g('Sun');
export const Sunrise = g('Sunrise');
export const Swords = g('Swords');
export const Table2 = g('Table2');
export const Tag = g('Tag');
export const Target = g('Target');
export const ThumbsDown = g('ThumbsDown');
export const Trash2 = g('Trash2');
export const TrendingDown = g('TrendingDown');
export const TrendingUp = g('TrendingUp');
export const TriangleAlert = g('TriangleAlert');
export const Trophy = g('Trophy');
export const Type = g('Type');
export const Upload = g('Upload');
export const User = g('User');
export const UserSearch = g('UserSearch');
export const Users = g('Users');
export const Volume2 = g('Volume2');
export const Wand = g('Wand');
export const X = g('X');
export const Zap = g('Zap');
