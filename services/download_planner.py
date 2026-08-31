"""Planificador único de descargas (puro, sin UI).

Consolida la construcción de `DownloadTask` que estaba duplicada en:

- `ui/download_controller.py` (_build_download_tasks)
- `syops_wizard.py` (run_download / run_fullpack)
- `syops_cli.py` (cmd_descargar)

Entrada: la lista `downloadable` (ya expandida por `build_download_apps`),
el método Adobe, si es Full Pack y la carpeta destino. Salida: un
`DownloadPlan` con tareas, warnings, apps sin link y requisitos de
resolución por navegador (worker). Las vistas (UI / wizard / CLI) ejecutan
el mismo plan; las instrucciones.txt dependen de la selección ORIGINAL del
usuario y cada vista las escribe con su propia lista.
"""

from pathlib import Path

from catalog.data import ADOBE_APPS
from catalog.tools import _app_tools_for_app
from catalog.adobe_helpers import (
    _adobe_best_link, _adobe_full_pack_links, _adobe_tools_for_method,
)
from services.download_resolvers import (
    _missing_download_links, _validate_link_format,
)
from services.resolver_gateway import (
    _resolve_download_link, URL_RESOLVERS, _pixeldrain_direct_url,
    is_appstorrent_url, has_resolver, get_resolver,
)
from services.download_manager import DownloadTask
from app_config import GENP_URL


class DownloadPlan:
    """Plan de descarga: qué bajar, con qué avisos y requisitos."""

    def __init__(self, tasks: list, warnings: list, missing: list,
                 resolver_requirements: list):
        self.tasks = tasks
        self.warnings = warnings
        self.missing = missing
        self.resolver_requirements = resolver_requirements

    @property
    def ok_count(self) -> int:
        return len(self.tasks) - len([t for t in self.tasks if t.status == "failed"])


def _provider_task(provider, kind: str, name: str, method: str, platform: str,
                   output_dir: Path, priority: int, size_hint: int):
    """Modo servidor (Tier 2): pide el link firmado y arma la tarea.

    No resuelve ninguna URL localmente. Devuelve (DownloadTask, warning).
    """
    from services.download_link_provider import DownloadLinkError
    from services.torbox_provider import torbox_enabled, torbox_supports

    def _method_for(url: str) -> str:
        """Método de la tarea para una URL.

        Con TorBox activado: un magnet se baja vía debrid (el cliente nunca
        entra al swarm de torrents) → ``torbox``; un hoster que TorBox cubre
        (``torbox_supports``) también → ``torbox``; un hoster que TorBox NO
        cubre (pixeldrain, workupload, …) → ``http`` (resolver -> directo).
        Sin TorBox → torrent/http como antes.
        """
        if url.startswith("magnet:"):
            return "torbox" if torbox_enabled() else "torrent"
        if torbox_enabled() and torbox_supports(url):
            return "torbox"
        return "http"

    try:
        data = provider.request(name, method, platform, kind=kind)
    except DownloadLinkError as exc:
        return None, f"{name}: {exc}"
    url = data["url"]
    display = data["name"]
    # El servidor puede indicar qué resolver usa la app (campo `resolver`).
    # Se activa SOLO ese resolver (lazy por app); si no está disponible,
    # se degrada a descarga directa con aviso.
    callback = None
    hint = (data.get("resolver") or "").strip().lower()
    if hint:
        if has_resolver(hint):
            kwargs = {"link": url, "app": display}
            if hint == "appstorrent":
                kwargs["dest_dir"] = output_dir
            callback = get_resolver(hint, **kwargs)
            # Con TorBox activo y URL que TorBox cubre (magnet o hoster en
            # TORBOX_SUPPORTED_HOSTS), bajamos DIRECTO por TorBox, SIN correr
            # el resolver en el cliente → el cliente no toca la fuente (una IP).
            # Si TorBox no cubre la URL (pixeldrain/workupload…), usamos el
            # resolver → directo en el cliente.
            task_method = _method_for(url)
            resolver_cb = None if task_method == "torbox" else callback
            return DownloadTask(display, task_method, url, output_dir, size_hint,
                                priority=priority, resolver_callback=resolver_cb), None
        else:
            task = DownloadTask(display, _method_for(url), url, output_dir,
                                size_hint, priority=priority)
            return task, f"{name}: resolver '{hint}' no disponible; descarga directa"
    return DownloadTask(display, _method_for(url), url, output_dir, size_hint,
                        priority=priority, resolver_callback=callback), None


def _task_for_app(app: str, adobe_method: str, output_dir: Path,
                  adobe_as_regular: bool = False, provider=None,
                  platform: str = None):
    """Construye la tarea de UNA app (Adobe, GenP o link directo/resolver).

    Devuelve (DownloadTask, warning): exactamente uno de los dos no es None.

    Con `adobe_as_regular=True` (flujo GenP en Windows, sin método Adobe)
    las apps Adobe se tratan como apps genéricas con link directo.

    Con `provider` (Tier 2) la URL se pide al servidor; no se resuelve nada
    localmente.
    """
    if provider is not None:
        if app == "GenP":
            return _provider_task(provider, "app", "GenP", "http", platform,
                                  output_dir, 0, 200 * 1024 ** 3)
        if adobe_as_regular:
            return _provider_task(provider, "app", app, "http", platform,
                                  output_dir, 0, 4 * 1024 ** 3)
        return _provider_task(provider, "adobe", app,
                              adobe_method or "aio_macked", platform,
                              output_dir, 0, 4 * 1024 ** 3)

    if app in ADOBE_APPS and not adobe_as_regular:
        url, version = _adobe_best_link(adobe_method, app)
        if not url:
            return None, f"{app}: sin link para método '{adobe_method}'"
        link = _pixeldrain_direct_url(url)
        display = f"{app} {version}".strip() if version else app
        return DownloadTask(display, "http", link, output_dir, 4 * 1024 ** 3), None

    if app == "GenP":
        return DownloadTask(app, "http", GENP_URL, output_dir, 200 * 1024 ** 3), None

    method, link = _resolve_download_link(app)
    if method == "manual" or not link:
        return None, f"{app}: método manual o sin link"

    fmt_error = _validate_link_format(method, link)
    if fmt_error:
        task = DownloadTask(app, method, link, output_dir, 0)
        task.status = "failed"
        task.error_msg = fmt_error
        return task, None

    for detector, factory in URL_RESOLVERS:
        if detector(link):
            kwargs = {"link": link, "app": app}
            if detector is is_appstorrent_url:
                kwargs["dest_dir"] = output_dir
            return DownloadTask(app, "http", link, output_dir, 4 * 1024 ** 3,
                                resolver_callback=factory(**kwargs)), None

    size_hint = 8 * 1024 ** 3 if method in ("torrent", "torbox") else 4 * 1024 ** 3
    return DownloadTask(app, method, link, output_dir, size_hint), None


def plan_downloads(downloadable: list, output_dir: Path,
                   adobe_method: str = None, adobe_fullpack: bool = False,
                   link_provider=None, platform: str = None,
                   sheet_items: list = None) -> DownloadPlan:
    """Construye el plan de descarga completo (apps + tools Adobe + tools por app).

    - Full Pack: baja el collection AIO completo (ignora `downloadable`).
    - Adobe por método: apps del método + sus tools (prioridad 1).
    - Apps genéricas: link directo, resolver de navegador o GenP.
    - Tools por app: se deduplican (una vez aunque varias apps las compartan).

    Sin método Adobe (Windows/GenP) las apps Adobe caen al flujo genérico
    con sus links directos.

    Con `link_provider` (Tier 2) las URLs se piden al servidor; el plan solo
    usa nombres/métodos locales (sin resolver links).
    """
    if link_provider is not None:
        return _plan_via_server(downloadable, output_dir, adobe_method,
                                adobe_fullpack, link_provider, platform,
                                sheet_items)

    tasks, warnings = [], []
    tiene_adobe = any(a in ADOBE_APPS for a in downloadable)
    # La rama Adobe SOLO corre si el llamador pasó un método: sin método
    # (Windows/GenP) las apps Adobe caen al flujo genérico con links directos.
    adobe_branch = bool(adobe_method and tiene_adobe)

    missing = _missing_download_links(
        [a for a in downloadable if a != "GenP" and a not in ADOBE_APPS]
    )

    if adobe_fullpack:
        for name, link in _adobe_full_pack_links(adobe_method or "aio_macked"):
            if not link:
                continue
            tasks.append(DownloadTask(name, "http", _pixeldrain_direct_url(link),
                                      output_dir, 8 * 1024 ** 3, priority=0))

    elif adobe_branch:
        adobe_metodo = adobe_method or "macked"
        if adobe_metodo == "activation_tool":
            # Este método no descarga apps individuales: se usa Adobe
            # Downloader (misma regla que la UI). Solo baja las tools.
            warnings.append("activation_tool no descarga apps: usá Adobe "
                            "Downloader (las tools se bajan igual)")
        for app in [a for a in downloadable if a in ADOBE_APPS]:
            task, warn = _task_for_app(app, adobe_metodo, output_dir)
            (tasks.append(task) if task else warnings.append(warn))
        for tool_name, tool_link in _adobe_tools_for_method(adobe_metodo,
                                                            sheet_items):
            if tool_link:
                tasks.append(DownloadTask(tool_name, "http",
                                          _pixeldrain_direct_url(tool_link),
                                          output_dir, 2 * 1024 ** 3, priority=1))

    for app in downloadable:
        # Las apps Adobe ya fueron planificadas por la rama Adobe (o el
        # Full Pack). Sin método Adobe (GenP en Windows) caen al flujo
        # genérico con sus links directos.
        if app in ADOBE_APPS and (adobe_branch or adobe_fullpack):
            continue
        task, warn = _task_for_app(app, adobe_method or "macked", output_dir,
                                   adobe_as_regular=True)
        (tasks.append(task) if task else warnings.append(warn))

    # Tools por app: acompañan a las apps seleccionadas (prioridad baja).
    # Las apps Adobe NO llevan tools por app: sus tools (Sentinel,
    # Pop-Up Blocker…) las aporta la rama del método Adobe. Si no hay método
    # (Windows/GenP) la app se baja fresca por torrent → sin tools.
    # Deduplicar por nombre: una misma tool (ej. Sentinel) solo se
    # descarga UNA vez aunque varias apps la compartan. Se inicializa
    # con las tools del método Adobe y las apps ya descargadas.
    seen_tools = set(downloadable)
    if adobe_method:
        seen_tools.update(name for name, _ in _adobe_tools_for_method(adobe_method,
                                                                      sheet_items))
    for app in downloadable:
        if app in ADOBE_APPS:
            continue
        for tool in _app_tools_for_app(app, sheet_items):
            tool_name = tool.get("name", app)
            if tool_name in seen_tools:
                continue
            seen_tools.add(tool_name)
            tool_link = tool.get("url", "")
            if not tool_link:
                continue
            tasks.append(DownloadTask(tool_name, "http",
                                      _pixeldrain_direct_url(tool_link),
                                      output_dir, 2 * 1024 ** 3, priority=1))

    resolver_requirements = [
        t.name for t in tasks if t.resolver_callback is not None
    ]
    return DownloadPlan(tasks, warnings, missing, resolver_requirements)


def _plan_via_server(downloadable, output_dir, adobe_method, adobe_fullpack,
                     provider, platform, sheet_items=None):
    """Modo servidor (Tier 2): todas las URLs se piden al servidor.

    Solo se usan localmente los NOMBRES de apps/tools y el método; ninguna
    URL de file-host se resuelve en el cliente.
    """
    tasks, warnings = [], []
    tiene_adobe = any(a in ADOBE_APPS for a in downloadable)
    adobe_branch = bool(adobe_method and tiene_adobe)

    if adobe_fullpack:
        for app in ADOBE_APPS:
            task, warn = _provider_task(provider, "adobe", app,
                                        adobe_method or "aio_macked", platform,
                                        output_dir, 0, 8 * 1024 ** 3)
            (tasks.append(task) if task else warnings.append(warn))
    elif adobe_branch:
        adobe_metodo = adobe_method or "macked"
        if adobe_metodo == "activation_tool":
            warnings.append("activation_tool no descarga apps: usá Adobe "
                            "Downloader (las tools se bajan igual)")
        for app in [a for a in downloadable if a in ADOBE_APPS]:
            task, warn = _provider_task(provider, "adobe", app, adobe_metodo,
                                        platform, output_dir, 0, 4 * 1024 ** 3)
            (tasks.append(task) if task else warnings.append(warn))
        for tool_name, _link in _adobe_tools_for_method(adobe_metodo,
                                                        sheet_items):
            task, warn = _provider_task(provider, "tool", tool_name,
                                        adobe_metodo, platform,
                                        output_dir, 1, 2 * 1024 ** 3)
            (tasks.append(task) if task else warnings.append(warn))

    for app in downloadable:
        if app in ADOBE_APPS and (adobe_branch or adobe_fullpack):
            continue
        task, warn = _task_for_app(app, adobe_method or "macked", output_dir,
                                   adobe_as_regular=True, provider=provider,
                                   platform=platform)
        (tasks.append(task) if task else warnings.append(warn))

    seen_tools = set(downloadable)
    if adobe_method:
        seen_tools.update(name for name, _ in _adobe_tools_for_method(adobe_method,
                                                                      sheet_items))
    for app in downloadable:
        if app in ADOBE_APPS:
            continue
        for tool in _app_tools_for_app(app, sheet_items):
            tool_name = tool.get("name", app)
            if tool_name in seen_tools:
                continue
            seen_tools.add(tool_name)
            task, warn = _provider_task(provider, "tool", tool_name,
                                        adobe_method or "", platform,
                                        output_dir, 1, 2 * 1024 ** 3)
            (tasks.append(task) if task else warnings.append(warn))

    return DownloadPlan(tasks, warnings, [], [])
