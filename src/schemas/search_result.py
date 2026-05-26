from marshmallow import Schema, fields


class SearchResultSchema(Schema):
    url = fields.Str(required=True)
    title = fields.Str(required=True)
    date_published = fields.DateTime(required=True)
    excerpt = fields.Str(required=True)
