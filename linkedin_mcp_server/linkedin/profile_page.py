"""Identity a loaded person page states about itself."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from linkedin_mcp_server.linkedin.session import PageSession


class MessageTarget(Protocol):
    """The recipient identity a top-card compose action carries."""

    @property
    def profile_urn(self) -> str: ...


class MessageTargetResolution(Protocol):
    """One attempt at reading that identity off the current page."""

    @property
    def target(self) -> MessageTarget | None: ...


# The URN is read out of the same atomic top-card snapshot the messaging
# workflow resolves its recipient from, and that read still belongs to the
# facade until the message sender owns it. Taking it as a callable keeps the
# borrow explicit and one-directional: this module never learns what the
# facade is, and the day the sender owns the read, only the wiring moves.
ReadMessageTarget = Callable[[], Awaitable[MessageTargetResolution]]


class ProfilePageReader:
    """Read the profile URN and display name off the bound person page."""

    def __init__(
        self,
        session: PageSession,
        read_message_target: ReadMessageTarget,
    ):
        self._session = session
        self._read_message_target = read_message_target

    async def _extract_profile_urn(self) -> str | None:
        """Extract a profile URN only from one unambiguous top-card snapshot."""
        resolution = await self._read_message_target()
        return resolution.target.profile_urn if resolution.target else None

    async def _read_profile_display_name(self) -> str | None:
        """Read the visible profile name from the current person page."""
        display_name = await self._session.run_on_linkedin(
            """() => {
                const heading = document.querySelector('main h1');
                const normalize = value => (value || '').replace(/\\s+/g, ' ').trim();
                if (heading) {
                    const headingText = normalize(
                        heading.innerText || heading.textContent || ''
                    );
                    if (headingText) return headingText;
                }

                const main = document.querySelector('main');
                if (!main) return '';
                const lines = (main.innerText || '')
                    .split('\\n')
                    .map(normalize)
                    .filter(Boolean);
                return lines[0] || '';
            }"""
        )
        if not isinstance(display_name, str):
            return None
        display_name = display_name.strip()
        return display_name or None

    async def extract_profile_image_url(self) -> str | None:
        """Return the public top-card headshot URL on the loaded profile page.

        LinkedIn profile reads intentionally use text extraction for most
        fields, but an image is not represented in ``innerText``.  Keep this
        narrow DOM read beside the other top-card identity reads and return
        only an absolute http(s) source URL.
        """
        image_url = await self._session.run_on_linkedin(
            """() => {
                const main = document.querySelector('main');
                if (!main) return '';
                const images = main.querySelectorAll(
                    'img.pv-top-card-profile-picture__image, '
                    + 'img[class*="profile-picture"], '
                    + 'img[alt*="profile picture" i], '
                    + 'img[alt*="profile photo" i]'
                );
                for (const image of images) {
                    const src = image.currentSrc || image.src || image.getAttribute('data-delayed-url') || '';
                    if (/^https?:\\/\\//i.test(src)) return src;
                }
                return '';
            }"""
        )
        if not isinstance(image_url, str):
            return None
        image_url = image_url.strip()
        return image_url if image_url.startswith(("https://", "http://")) else None
