from marshmallow import Schema, fields
from datetime import date, datetime


class ArticleDate(fields.Date):
    """Accept both ISO date strings and SQLAlchemy's native date values."""

    def _deserialize(self, value, attr, data, **kwargs):
        if isinstance(value, datetime):
            value = value.date()
        if isinstance(value, date):
            value = value.isoformat()
        return super()._deserialize(value, attr, data, **kwargs)


class SearchResultSchema(Schema):
    url = fields.Str(required=True)
    title = fields.Str(required=True)
    # Article dates are stored and returned as date-only values (not timestamps).
    date_published = ArticleDate(required=True, allow_none=True)
    excerpt = fields.Str(required=True)
