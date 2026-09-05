# engine/agents_glm/news_sentiment_agent.py
import logging

logger = logging.getLogger("aura.agent.sentiment")

SENTIMENT_ENABLED = False


class NewsSentimentAgent:
    def __init__(self):
        self.analyzer = None
        if not SENTIMENT_ENABLED:
            return
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            self.analyzer = SentimentIntensityAnalyzer()
        except Exception as e:
            logger.error("vaderSentiment ausente: %s", e)

    def analyze_news(self, news_text: str) -> str:
        if not self.analyzer:
            return "SENTIMENT_DISABLED"
        vs = self.analyzer.polarity_scores(news_text)
        compound = vs["compound"]
        if compound <= -0.5:
            return "MUITO NEGATIVO"
        if compound >= 0.5:
            return "POSITIVO"
        return "NEUTRO"


SENTIMENT_AGENT = NewsSentimentAgent()
