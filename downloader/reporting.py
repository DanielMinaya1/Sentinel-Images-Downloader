"""
Human-readable reports built from the typed download-status objects
(`downloader.models.status`). Used by the CLI and available to any
programmatic caller of `downloader.api`.
"""


from downloader.models import DownloadStatus, RunSummary, TileDownloadSummary


def _format_tile_lines(tile: TileDownloadSummary) -> list[str]:
    lines = [
        f"Tile {tile.tile_id}: {len(tile.products)} product(s) - "
        f"{tile.succeeded} succeeded, {tile.failed} failed, {tile.skipped} skipped"
    ]

    for product in tile.products:
        lines.append(
            f"  - {product.product_name} [{product.status.value.upper()}]: "
            f"{product.succeeded} succeeded, {product.failed} failed, "
            f"{product.skipped} skipped"
        )
        if product.error:
            lines.append(f"      error: {product.error}")
        for file_result in product.files:
            if file_result.status == DownloadStatus.FAILED:
                lines.append(
                    f"      FAILED: {file_result.file_path} - {file_result.error}"
                )

    return lines


def format_tile_report(tile: TileDownloadSummary) -> str:
    """Formats the outcome of a single `download_tile()` call."""
    return "\n".join(_format_tile_lines(tile))


def format_run_report(run: RunSummary) -> str:
    """Formats the outcome of a full `download()` run, across every tile."""
    lines = [
        "=== Download Summary ===",
        f"Tiles: {len(run.tiles)}  Succeeded: {run.succeeded}  "
        f"Failed: {run.failed}  Skipped: {run.skipped}",
    ]

    for tile in run.tiles:
        lines.append("")
        lines.extend(_format_tile_lines(tile))

    return "\n".join(lines)
