import unittest

from cogs.embeds import (
    DEFAULT_BANNER_URL,
    DEFAULT_THUMBNAIL_URL,
    DEFAULT_TICKET_BUTTON_URL,
    EmbedDraft,
    validate_web_url,
)


class EmbedImageDefaultsTests(unittest.TestCase):
    def test_new_draft_uses_default_images(self):
        draft = EmbedDraft(channel=object())

        self.assertEqual(draft.banner_url, DEFAULT_BANNER_URL)
        self.assertEqual(draft.thumbnail_url, DEFAULT_THUMBNAIL_URL)

    def test_custom_image_replaces_default(self):
        custom_url = "https://example.com/custom.png"

        self.assertEqual(validate_web_url(custom_url, "La imagen"), custom_url)

    def test_empty_image_field_disables_image(self):
        self.assertIsNone(validate_web_url("   ", "La imagen"))

    def test_default_ticket_button_url_is_valid(self):
        self.assertEqual(
            validate_web_url(DEFAULT_TICKET_BUTTON_URL, "El enlace del botón"),
            DEFAULT_TICKET_BUTTON_URL,
        )


if __name__ == "__main__":
    unittest.main()
