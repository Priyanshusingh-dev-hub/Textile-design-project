"""Portable .textileproj files.

A project is a zip the user keeps on their own disk: project.json (palette,
layer list, workspace settings) plus every image it needs as PNG. Nothing
depends on the server's temporary image store, so a saved project still
opens after the working files have been cleaned up, after a restart, or on
another machine.
"""
import json
from io import BytesIO
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile
from PIL import Image

FORMAT = 'loomlab-project'
VERSION = 2
MAX_LAYERS = 64
_MAX_JSON_BYTES = 5 * 1024 * 1024
_MAX_IMAGE_BYTES = 1024 * 1024 * 1024  # decompressed, per image


def pack(meta: dict, original: Image.Image | None, current: Image.Image | None, layers: list[Image.Image]) -> bytes:
    """meta: palette/settings/name plus `layers` -- one dict per layer image,
    in the same order. Image paths inside the zip are filled in here."""
    meta = dict(meta, format=FORMAT, version=VERSION)
    buf = BytesIO()
    with ZipFile(buf, 'w', ZIP_DEFLATED) as zf:
        def put(path, image):
            page = BytesIO(); image.convert('RGBA').save(page, format='PNG'); zf.writestr(path, page.getvalue())
            return path
        meta['original'] = put('images/original.png', original) if original is not None else None
        meta['image'] = put('images/current.png', current) if current is not None else None
        meta['layers'] = [dict(info, file=put(f'layers/{i + 1:02d}.png', img)) for i, (info, img) in enumerate(zip(meta.get('layers', []), layers))]
        zf.writestr('project.json', json.dumps(meta, indent=2))
    return buf.getvalue()


def unpack(raw: bytes):
    """Returns (meta, original, current, [(layer_info, layer_image)]).
    Raises ValueError with a user-facing message for anything that is not a
    readable LoomLab project."""
    try:
        zf = ZipFile(BytesIO(raw))
    except BadZipFile:
        raise ValueError('This is not a LoomLab project file (.textileproj).')
    with zf:
        try:
            meta = json.loads(_read(zf, 'project.json', _MAX_JSON_BYTES))
        except json.JSONDecodeError:
            raise ValueError('The project file is damaged (project.json is not valid JSON).')
        if not isinstance(meta, dict) or meta.get('format') != FORMAT:
            raise ValueError('This is not a LoomLab project file (.textileproj).')
        if not isinstance(meta.get('version'), int) or meta['version'] > VERSION:
            raise ValueError('This project was saved by a newer version of LoomLab.')
        layers = meta.get('layers') or []
        if not isinstance(layers, list) or len(layers) > MAX_LAYERS:
            raise ValueError('The project file has an invalid layer list.')
        original = _image(zf, meta.get('original'))
        current = _image(zf, meta.get('image'))
        loaded = []
        for info in layers:
            if not isinstance(info, dict):
                raise ValueError('The project file has an invalid layer list.')
            img = _image(zf, info.get('file'))
            if img is not None:
                loaded.append((info, img))
    return meta, original, current, loaded


def _read(zf: ZipFile, name: str, limit: int) -> bytes:
    try:
        info = zf.getinfo(name)
    except KeyError:
        raise ValueError(f'The project file is missing {name}.')
    if info.file_size > limit:
        raise ValueError(f'{name} in the project file is too large.')
    try:
        return zf.read(info)
    except Exception as e:
        raise ValueError(f'The project file is damaged ({name}): {e}')


def _image(zf: ZipFile, name) -> Image.Image | None:
    if not name:
        return None
    if not isinstance(name, str):
        raise ValueError('The project file has an invalid image reference.')
    try:
        img = Image.open(BytesIO(_read(zf, name, _MAX_IMAGE_BYTES)))
        img.load()
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f'The project file has an unreadable image ({name}): {e}')
    return img.convert('RGBA')
