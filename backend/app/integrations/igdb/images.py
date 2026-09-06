IGDB_COVER_URL_PREFIX = (
    "https://images.igdb.com/igdb/image/upload/t_cover_big/"
)


def igdb_cover_url(cover_image_id: str | None) -> str | None:
    """Build an IGDB cover URL only from an already-cached image ID."""
    if cover_image_id is None:
        return None
    return f"{IGDB_COVER_URL_PREFIX}{cover_image_id}.jpg"
