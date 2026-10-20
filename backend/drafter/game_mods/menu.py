"""A Dota 2 main-menu background pack: pakNN_dir.vpk for a game/dota_<language>/ folder.

Port of GridStudio's scripts/menu-background.mjs (https://github.com/linsisss/dota2-grid-toolkit,
GPL-3.0-only); what is ported is what GridStudio tested in the game (docs/customize.md there):
  * the menu: the dashboard's background manager loads whatever layout its override-background
    names; the pack replaces dashboard.vxml_c with Valve's current layout naming ours instead, and
    ours plays the user's video full screen;
  * `clean`: the home page without its news column (#TodayPages), so nothing covers the video;
  * the hero page (behind the hero model): the menu's video, a video of its own, or Valve's picture;
  * the «Герои» page (under the hero grid): as the menu, darker, or a video of its own.
Dota is strict: a new layout must not have event handlers and no file may have non-ASCII text
(either makes the client stop with «Unable to load layout file»), so every file is checked.
Valve's layouts come from shared/dota-menu (see its README).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .. import config
from .vpk import build_vpk, panorama_resource

LIMITS = {"video_bytes": 16_000_000, "seconds": 30}

MENU_VIDEO = "panorama/videos/drafter_background.webm"
MENU_LAYOUT = "panorama/layout/drafter_background.vxml_c"
MENU_STYLE = "panorama/styles/drafter_background.vcss_c"
DASHBOARD = "panorama/layout/dashboard.vxml_c"
HOME = "panorama/layout/dashboard_page_home.vxml_c"

HERO_PAGE = "panorama/layout/dashboard_page_hero_new_v2.vxml_c"
HERO_STYLE = "panorama/styles/drafter_hero_background.vcss_c"
HERO_VIDEO = "panorama/videos/drafter_hero_background.webm"
HERO_OPACITY = 0.6  # Valve's picture is shown at 0.3; the builder's preview matches this

GRID_PAGE = "panorama/layout/dashboard_page_heroes.vxml_c"
GRID_STYLE = "panorama/styles/drafter_grid.vcss_c"
GRID_VIDEO = "panorama/videos/drafter_grid_background.webm"
GRID_DIM_MAX = 0.9

LAYOUT = f"""<root>
	<styles>
		<include src="s2r://panorama/styles/dotastyles.vcss_c" />
		<include src="s2r://{MENU_STYLE}" />
	</styles>
	<Panel class="DrafterBackground" hittest="false">
		<MoviePanel id="DrafterMovie" src="s2r://{MENU_VIDEO}" repeat="true" autoplay="onload" hittest="false" />
	</Panel>
</root>
"""
STYLE = """.DrafterBackground
{
	width: 100%;
	height: 100%;
	background-color: black;
}

#DrafterMovie
{
	width: 100%;
	height: 100%;
}
"""
HERO_STYLE_TEXT = f"""/* Dota Drafter: a video behind the hero instead of Valve's seasonal picture. */
.DashboardPage #HeroLoadoutBackgroundImageContainer
{{
	background-color: black;
	blur: gaussian(0px);
	saturation: 1;
}}

.DashboardPage #HeroLoadoutBackgroundImageContainer #HeroLoadoutBackgroundImage
{{
	visibility: collapse;
}}

#DrafterHeroMovie
{{
	width: 100%;
	height: 100%;
	opacity: {HERO_OPACITY};
	transition-property: opacity, transform;
	transition-duration: 1s;
	transition-timing-function: cubic-bezier(0, 1, 0, 1);
}}

.EnableHeroCustomize #DrafterHeroMovie
{{
	opacity: 0.1;
	transform: translateX( -60px );
}}
"""
HERO_INCLUDE = '<include src="s2r://panorama/styles/hero_loadout_background_images.vcss_c" />'
HERO_CONTAINER = re.compile(r'(<Panel id="HeroLoadoutBackgroundImageContainer" hittest="false">\n)')
GRID_INCLUDE = '<include src="s2r://panorama/styles/dashboard_page_heroes.vcss_c" />'
GRID_ROOT = '<DOTAHeroesPage class="DashboardPage" defaultfocus="HeroGrid">'


class PackError(Exception):
    """The pack cannot be built (the message is for the user)."""


def menu_dir() -> Path:
    return config.SHARED / "dota-menu"


def valve_layout(name: str) -> str:
    return (menu_dir() / name).read_text(encoding="utf-8")


def valve_meta() -> dict:
    return json.loads((menu_dir() / "meta.json").read_text(encoding="utf-8"))


def _once(text: str, find: str, replace: str, what: str) -> str:
    if text.count(find) != 1:
        raise PackError(f"в {what} не найдено нужное место: файлы меню устарели")
    return text.replace(find, replace)


def menu_dashboard(dashboard: str) -> str:
    pattern = re.compile(r'(<DOTADashboardBackgroundManager\b[^>]*\boverride-background=")[^"]*(")')
    if len(pattern.findall(dashboard)) != 1:
        raise PackError("в dashboard.xml не найден DOTADashboardBackgroundManager с override-background")
    return pattern.sub(lambda m: f"{m.group(1)}s2r://{MENU_LAYOUT}{m.group(2)}", dashboard)


def clean_home(home: str) -> str:
    cleaned = re.sub(r'\n?[ \t]*<Panel id="TodayPages"[\s\S]*?\n[ \t]*</Panel>(?=\n[ \t]*</DOTAHomePage>)', "", home, count=1)
    if cleaned == home:
        raise PackError("в dashboard_page_home.xml не найден блок #TodayPages")
    return cleaned


def hero_page(page: str, video: str) -> str:
    if page.count(HERO_INCLUDE) != 1 or not HERO_CONTAINER.search(page):
        raise PackError("в dashboard_page_hero_new_v2.xml не найден фон за героем")
    page = page.replace(HERO_INCLUDE, f'{HERO_INCLUDE}\n\t\t<include src="s2r://{HERO_STYLE}" />')
    movie = f'\t\t\t<MoviePanel id="DrafterHeroMovie" src="s2r://{video}" repeat="true" autoplay="onload" hittest="false" />\n'
    return HERO_CONTAINER.sub(lambda m: m.group(1) + movie, page, count=1)


def grid_page(page: str, own: bool) -> str:
    """The «Герои» page: a veil over the menu's background, or a video of its own (the menu's
    background hidden there, as Valve's hero page does)."""
    if page.count(GRID_INCLUDE) != 1 or page.count(GRID_ROOT) != 1:
        raise PackError("в dashboard_page_heroes.xml не найдена страница «Герои»")
    layer = (f'<MoviePanel id="DrafterGridMovie" src="s2r://{GRID_VIDEO}" repeat="true" autoplay="onload" hittest="false" />'
             if own else '<Panel id="DrafterGridVeil" hittest="false" />')
    root = GRID_ROOT.replace(">", ' hidebackground="true">') if own else GRID_ROOT
    page = page.replace(GRID_INCLUDE, f'{GRID_INCLUDE}\n\t\t<include src="s2r://{GRID_STYLE}" />')
    return page.replace(GRID_ROOT, f"{root}\n\t\t{layer}")


def grid_style(dim: float | None) -> str:
    text = """/* Dota Drafter: the background under the hero grid. */
#DrafterGridMovie,
#DrafterGridVeil
{
	width: 100%;
	height: 1080px;
	margin-top: -120px;
}
"""
    if dim is not None:
        alpha = round(max(0.0, min(GRID_DIM_MAX, float(dim))) * 255)
        text += f"\n#DrafterGridVeil\n{{\n\tbackground-color: #000000{alpha:02x};\n}}\n"
    return text


def _panorama(path: str, source: str, valve: bool = False) -> tuple[str, bytes]:
    if re.search(r"[^\x00-\x7f]", source):
        raise PackError(f"не-ASCII в {path}: Дота не загрузит меню")
    if not valve and path.endswith(".vxml_c") and re.search(r'\son[a-z]+="', source):
        raise PackError(f"обработчик событий в новой разметке {path}: Дота не загрузит меню")
    return path, panorama_resource(path, source)


def _webm(data: bytes, what: str) -> bytes:
    if data[:4] != b"\x1a\x45\xdf\xa3":
        raise PackError(f"{what}: нужен файл WebM")
    if len(data) > LIMITS["video_bytes"]:
        raise PackError(f"{what}: видео больше {LIMITS['video_bytes'] // 1_000_000} МБ — Дота покажет чёрное меню")
    return data


def build_pack(video: bytes | None, *, clean: bool = False, hero: str = "off", hero_video: bytes | None = None,
               grid: str = "menu", grid_dim: float = 0.5, grid_video: bytes | None = None) -> bytes:
    """hero: 'off' (Valve's picture), 'menu' (the menu's video), 'own' (hero_video).
    grid: 'menu' (as is), 'dim' (a veil of grid_dim), 'own' (grid_video)."""
    files: list[tuple[str, bytes]] = []
    if video is not None:
        files += [
            _panorama(DASHBOARD, menu_dashboard(valve_layout("dashboard.xml")), valve=True),
            _panorama(MENU_LAYOUT, LAYOUT),
            _panorama(MENU_STYLE, STYLE),
            (MENU_VIDEO, _webm(video, "фон меню")),
        ]
    if clean:
        files.append(_panorama(HOME, clean_home(valve_layout("dashboard_page_home.xml")), valve=True))
    if hero in ("menu", "own"):
        if hero == "menu" and video is None:
            raise PackError("за героем «как в меню» нужен фон меню")
        if hero == "own" and hero_video is None:
            raise PackError("нет видео для фона за героем")
        files.append(_panorama(HERO_PAGE, hero_page(valve_layout("dashboard_page_hero_new_v2.xml"),
                                                    HERO_VIDEO if hero == "own" else MENU_VIDEO), valve=True))
        files.append(_panorama(HERO_STYLE, HERO_STYLE_TEXT))
        if hero == "own":
            files.append((HERO_VIDEO, _webm(hero_video, "фон за героем")))
    if grid in ("dim", "own"):
        if grid == "own" and grid_video is None:
            raise PackError("нет видео для фона под сеткой")
        files.append(_panorama(GRID_PAGE, grid_page(valve_layout("dashboard_page_heroes.xml"), grid == "own"), valve=True))
        files.append(_panorama(GRID_STYLE, grid_style(None if grid == "own" else grid_dim)))
        if grid == "own":
            files.append((GRID_VIDEO, _webm(grid_video, "фон под сеткой")))
    if not files:
        raise PackError("нечего собирать: выбери фон меню или фон страницы")
    return build_vpk(files)
