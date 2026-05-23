from enum import Enum


class PageKind(str, Enum):
    ARTICLE = "article"
    BLOG_INDEX = "blog_index"
    BLOG_POST = "blog_post"
    FORUM_THREAD = "forum_thread"
    HIERARCHICAL_THREAD = "hierarchical_thread"
    OTHER = "other"

    def __str__(self) -> str:
        return str(self.value)
