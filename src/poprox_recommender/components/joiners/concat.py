from poprox_concepts import ArticleSet
from poprox_recommender.lkpipeline import Component


class Concatenate(Component):
    def __call__(self, candidates1: ArticleSet, candidates2: ArticleSet) -> ArticleSet:
        """
        Concatenates two sets of candidates, while deduplicating them, keeping the
        first occurrence of each article (by id), and maintaining their original order.

        This is achieved by inserting articles into a dict in reverse order, so that
        articles from the second candidate set are written first and then overwritten
        by articles from the first candidate set (if there are collisions.) Afterward,
        the dict keys can be ignored and the dict values are the deduplicated candidates
        in reverse order. Reversing them one more time returns them to the original order.
        """
        reverse_articles = reversed(candidates1.articles + candidates2.articles)
        articles = {article.article_id: article for article in reverse_articles}

        return ArticleSet(articles=list(reversed(articles.values())))
