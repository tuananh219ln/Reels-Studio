"""A scheduled feed post whose id Facebook gave as the photo's: the post is found again by its text."""

from datetime import UTC, datetime, timedelta

from conftest import photo_bytes
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN

from reels_api import facebook

TEXT = "Ngày 3 | Dầu chiên đi chiên lại – nên hạn chế"


def page_with_a_live_reel(fakes) -> facebook.Page:
    """As in production: the Page has a reel the app saw live, so Facebook's (#100) for an id means "gone"."""
    fakes.reels["reel_live"] = {"uploaded": True, "bytes": 1, "finishes": 1, "state": "published"}
    return facebook.Page(FACEBOOK_PAGE, FACEBOOK_TOKEN, witnesses=("reel_live",))


def test_a_scheduled_photo_answered_with_the_photos_id_is_found_by_its_text(fakes, tmp_path):
    fakes.page_scheduled_photo_without_post_id = True
    page = page_with_a_live_reel(fakes)
    image = tmp_path / "card.jpg"
    image.write_bytes(photo_bytes())
    at = datetime.now(UTC) + timedelta(hours=5)

    remote = facebook.publish_photo(page, TEXT, image, at)

    assert facebook.post_status(page, remote) is None  # the photo's id is not a post Facebook can read
    settled = facebook.settle_post(page, remote, TEXT)
    (post_id,) = fakes.page_posts
    assert settled is not None and settled[0] == post_id
    assert settled[1]["published"] is False and settled[1]["scheduled_at"] == at.replace(microsecond=0)


def test_a_post_Facebook_really_lost_stays_lost(fakes):
    page = page_with_a_live_reel(fakes)
    assert facebook.settle_post(page, f"{FACEBOOK_PAGE}_404", TEXT) is None


def test_a_readable_post_is_returned_as_it_is(fakes):
    page = page_with_a_live_reel(fakes)
    remote = facebook.publish_text(page, TEXT, None)
    settled = facebook.settle_post(page, remote, TEXT)
    assert settled == (remote, {"published": True, "scheduled_at": None})
