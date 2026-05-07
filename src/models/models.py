from typing import Any, Optional
import datetime

from pgvector.sqlalchemy.vector import VECTOR
from sqlalchemy import ARRAY, BigInteger, Boolean, Column, Date, DateTime, Double, ForeignKeyConstraint, Index, Integer, PrimaryKeyConstraint, Table, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass


t_dates = Table(
    'dates', Base.metadata,
    Column('date_published', Text)
)


t_g1 = Table(
    'g1', Base.metadata,
    Column('id', BigInteger),
    Column('source_file', Text),
    Column('globaleventid', BigInteger),
    Column('sqldate', BigInteger),
    Column('monthyear', Integer),
    Column('year', Integer),
    Column('fractiondate', Double(53)),
    Column('actor1code', Text),
    Column('actor1name', Text),
    Column('actor1countrycode', Text),
    Column('actor1knowngroupcode', Text),
    Column('actor1ethniccode', Text),
    Column('actor1religion1code', Text),
    Column('actor1religion2code', Text),
    Column('actor1type1code', Text),
    Column('actor1type2code', Text),
    Column('actor1type3code', Text),
    Column('actor2code', Text),
    Column('actor2name', Text),
    Column('actor2countrycode', Text),
    Column('actor2knowngroupcode', Text),
    Column('actor2ethniccode', Text),
    Column('actor2religion1code', Text),
    Column('actor2religion2code', Text),
    Column('actor2type1code', Text),
    Column('actor2type2code', Text),
    Column('actor2type3code', Text),
    Column('isrootevent', Integer),
    Column('eventcode', Text),
    Column('eventbasecode', Text),
    Column('eventrootcode', Text),
    Column('quadclass', Integer),
    Column('goldsteinscale', Double(53)),
    Column('nummentions', Integer),
    Column('numsources', Integer),
    Column('numarticles', Integer),
    Column('avgtone', Double(53)),
    Column('actor1geo_type', Integer),
    Column('actor1geo_fullname', Text),
    Column('actor1geo_countrycode', Text),
    Column('actor1geo_adm1code', Text),
    Column('actor1geo_adm2code', Text),
    Column('actor1geo_lat', Double(53)),
    Column('actor1geo_long', Double(53)),
    Column('actor1geo_featureid', Text),
    Column('actor2geo_type', Integer),
    Column('actor2geo_fullname', Text),
    Column('actor2geo_countrycode', Text),
    Column('actor2geo_adm1code', Text),
    Column('actor2geo_adm2code', Text),
    Column('actor2geo_lat', Double(53)),
    Column('actor2geo_long', Double(53)),
    Column('actor2geo_featureid', Text),
    Column('actiongeo_type', Integer),
    Column('actiongeo_fullname', Text),
    Column('actiongeo_countrycode', Text),
    Column('actiongeo_adm1code', Text),
    Column('actiongeo_adm2code', Text),
    Column('actiongeo_lat', Double(53)),
    Column('actiongeo_long', Double(53)),
    Column('actiongeo_featureid', Text),
    Column('dateadded', BigInteger),
    Column('sourceurl', Text),
    Column('ingested_at', DateTime(True))
)


t_g1_count = Table(
    'g1_count', Base.metadata,
    Column('count', BigInteger)
)


t_g1_count_by_date = Table(
    'g1_count_by_date', Base.metadata,
    Column('date_published', Text),
    Column('count', BigInteger)
)


t_g1_gdelt = Table(
    'g1_gdelt', Base.metadata,
    Column('count', BigInteger)
)


class G1Sitemaps(Base):
    __tablename__ = 'g1_sitemaps'
    __table_args__ = (
        PrimaryKeyConstraint('sitemap_url', name='g1_sitemaps_pkey'),
    )

    sitemap_url: Mapped[str] = mapped_column(Text, primary_key=True)
    discovered_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    processed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    urls_in_sitemap: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    extracted_ok: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    extracted_failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    sitemap_lastmod: Mapped[Optional[str]] = mapped_column(Text)
    target_date: Mapped[Optional[datetime.date]] = mapped_column(Date)

    g1_articles: Mapped[list['G1Articles']] = relationship('G1Articles', back_populates='g1_sitemaps')


class GdeltBrazilEvents(Base):
    __tablename__ = 'gdelt_brazil_events'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='gdelt_brazil_events_pkey'),
        UniqueConstraint('source_file', 'globaleventid', 'sourceurl', name='gdelt_brazil_events_source_file_globaleventid_sourceurl_key'),
        Index('idx_gdelt_brazil_events_title_next_retry', 'title_next_retry_at'),
        Index('idx_gdelt_brazil_events_title_pending', 'sourceurl', postgresql_where='(title IS NULL)'),
        Index('idx_gdelt_brazil_source_url', 'sourceurl'),
        Index('idx_research_date_immutable')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    sourceurl: Mapped[str] = mapped_column(Text, nullable=False)
    ingested_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    title_fetch_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    globaleventid: Mapped[Optional[int]] = mapped_column(BigInteger)
    sqldate: Mapped[Optional[int]] = mapped_column(BigInteger)
    monthyear: Mapped[Optional[int]] = mapped_column(Integer)
    year: Mapped[Optional[int]] = mapped_column(Integer)
    fractiondate: Mapped[Optional[float]] = mapped_column(Double(53))
    actor1code: Mapped[Optional[str]] = mapped_column(Text)
    actor1name: Mapped[Optional[str]] = mapped_column(Text)
    actor1countrycode: Mapped[Optional[str]] = mapped_column(Text)
    actor1knowngroupcode: Mapped[Optional[str]] = mapped_column(Text)
    actor1ethniccode: Mapped[Optional[str]] = mapped_column(Text)
    actor1religion1code: Mapped[Optional[str]] = mapped_column(Text)
    actor1religion2code: Mapped[Optional[str]] = mapped_column(Text)
    actor1type1code: Mapped[Optional[str]] = mapped_column(Text)
    actor1type2code: Mapped[Optional[str]] = mapped_column(Text)
    actor1type3code: Mapped[Optional[str]] = mapped_column(Text)
    actor2code: Mapped[Optional[str]] = mapped_column(Text)
    actor2name: Mapped[Optional[str]] = mapped_column(Text)
    actor2countrycode: Mapped[Optional[str]] = mapped_column(Text)
    actor2knowngroupcode: Mapped[Optional[str]] = mapped_column(Text)
    actor2ethniccode: Mapped[Optional[str]] = mapped_column(Text)
    actor2religion1code: Mapped[Optional[str]] = mapped_column(Text)
    actor2religion2code: Mapped[Optional[str]] = mapped_column(Text)
    actor2type1code: Mapped[Optional[str]] = mapped_column(Text)
    actor2type2code: Mapped[Optional[str]] = mapped_column(Text)
    actor2type3code: Mapped[Optional[str]] = mapped_column(Text)
    isrootevent: Mapped[Optional[int]] = mapped_column(Integer)
    eventcode: Mapped[Optional[str]] = mapped_column(Text)
    eventbasecode: Mapped[Optional[str]] = mapped_column(Text)
    eventrootcode: Mapped[Optional[str]] = mapped_column(Text)
    quadclass: Mapped[Optional[int]] = mapped_column(Integer)
    goldsteinscale: Mapped[Optional[float]] = mapped_column(Double(53))
    nummentions: Mapped[Optional[int]] = mapped_column(Integer)
    numsources: Mapped[Optional[int]] = mapped_column(Integer)
    numarticles: Mapped[Optional[int]] = mapped_column(Integer)
    avgtone: Mapped[Optional[float]] = mapped_column(Double(53))
    actor1geo_type: Mapped[Optional[int]] = mapped_column(Integer)
    actor1geo_fullname: Mapped[Optional[str]] = mapped_column(Text)
    actor1geo_countrycode: Mapped[Optional[str]] = mapped_column(Text)
    actor1geo_adm1code: Mapped[Optional[str]] = mapped_column(Text)
    actor1geo_adm2code: Mapped[Optional[str]] = mapped_column(Text)
    actor1geo_lat: Mapped[Optional[float]] = mapped_column(Double(53))
    actor1geo_long: Mapped[Optional[float]] = mapped_column(Double(53))
    actor1geo_featureid: Mapped[Optional[str]] = mapped_column(Text)
    actor2geo_type: Mapped[Optional[int]] = mapped_column(Integer)
    actor2geo_fullname: Mapped[Optional[str]] = mapped_column(Text)
    actor2geo_countrycode: Mapped[Optional[str]] = mapped_column(Text)
    actor2geo_adm1code: Mapped[Optional[str]] = mapped_column(Text)
    actor2geo_adm2code: Mapped[Optional[str]] = mapped_column(Text)
    actor2geo_lat: Mapped[Optional[float]] = mapped_column(Double(53))
    actor2geo_long: Mapped[Optional[float]] = mapped_column(Double(53))
    actor2geo_featureid: Mapped[Optional[str]] = mapped_column(Text)
    actiongeo_type: Mapped[Optional[int]] = mapped_column(Integer)
    actiongeo_fullname: Mapped[Optional[str]] = mapped_column(Text)
    actiongeo_countrycode: Mapped[Optional[str]] = mapped_column(Text)
    actiongeo_adm1code: Mapped[Optional[str]] = mapped_column(Text)
    actiongeo_adm2code: Mapped[Optional[str]] = mapped_column(Text)
    actiongeo_lat: Mapped[Optional[float]] = mapped_column(Double(53))
    actiongeo_long: Mapped[Optional[float]] = mapped_column(Double(53))
    actiongeo_featureid: Mapped[Optional[str]] = mapped_column(Text)
    dateadded: Mapped[Optional[int]] = mapped_column(BigInteger)
    title: Mapped[Optional[str]] = mapped_column(Text)
    title_last_fetch_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    title_fetch_status: Mapped[Optional[str]] = mapped_column(Text)
    title_fetch_error: Mapped[Optional[str]] = mapped_column(Text)
    title_next_retry_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    article_content: Mapped[Optional[str]] = mapped_column(Text)


t_gdelt_brazil_events_enriched = Table(
    'gdelt_brazil_events_enriched', Base.metadata,
    Column('id', BigInteger),
    Column('source_file', Text),
    Column('globaleventid', BigInteger),
    Column('sqldate', BigInteger),
    Column('monthyear', Integer),
    Column('year', Integer),
    Column('fractiondate', Double(53)),
    Column('actor1code', Text),
    Column('actor1name', Text),
    Column('actor1countrycode', Text),
    Column('actor1knowngroupcode', Text),
    Column('actor1ethniccode', Text),
    Column('actor1religion1code', Text),
    Column('actor1religion2code', Text),
    Column('actor1type1code', Text),
    Column('actor1type2code', Text),
    Column('actor1type3code', Text),
    Column('actor2code', Text),
    Column('actor2name', Text),
    Column('actor2countrycode', Text),
    Column('actor2knowngroupcode', Text),
    Column('actor2ethniccode', Text),
    Column('actor2religion1code', Text),
    Column('actor2religion2code', Text),
    Column('actor2type1code', Text),
    Column('actor2type2code', Text),
    Column('actor2type3code', Text),
    Column('isrootevent', Integer),
    Column('eventcode', Text),
    Column('eventbasecode', Text),
    Column('eventrootcode', Text),
    Column('quadclass', Integer),
    Column('goldsteinscale', Double(53)),
    Column('nummentions', Integer),
    Column('numsources', Integer),
    Column('numarticles', Integer),
    Column('avgtone', Double(53)),
    Column('actor1geo_type', Integer),
    Column('actor1geo_fullname', Text),
    Column('actor1geo_countrycode', Text),
    Column('actor1geo_adm1code', Text),
    Column('actor1geo_adm2code', Text),
    Column('actor1geo_lat', Double(53)),
    Column('actor1geo_long', Double(53)),
    Column('actor1geo_featureid', Text),
    Column('actor2geo_type', Integer),
    Column('actor2geo_fullname', Text),
    Column('actor2geo_countrycode', Text),
    Column('actor2geo_adm1code', Text),
    Column('actor2geo_adm2code', Text),
    Column('actor2geo_lat', Double(53)),
    Column('actor2geo_long', Double(53)),
    Column('actor2geo_featureid', Text),
    Column('actiongeo_type', Integer),
    Column('actiongeo_fullname', Text),
    Column('actiongeo_countrycode', Text),
    Column('actiongeo_adm1code', Text),
    Column('actiongeo_adm2code', Text),
    Column('actiongeo_lat', Double(53)),
    Column('actiongeo_long', Double(53)),
    Column('actiongeo_featureid', Text),
    Column('dateadded', BigInteger),
    Column('sourceurl', Text),
    Column('ingested_at', DateTime(True)),
    Column('quadclass_label', Text),
    Column('quadclass_description', Text),
    Column('eventrootcode_label', Text),
    Column('actor1geo_type_label', Text),
    Column('actor2geo_type_label', Text),
    Column('actiongeo_type_label', Text)
)


class GdeltDimCameoRootEvent(Base):
    __tablename__ = 'gdelt_dim_cameo_root_event'
    __table_args__ = (
        PrimaryKeyConstraint('code', name='gdelt_dim_cameo_root_event_pkey'),
    )

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)


class GdeltDimCodedColumnDictionary(Base):
    __tablename__ = 'gdelt_dim_coded_column_dictionary'
    __table_args__ = (
        PrimaryKeyConstraint('column_name', name='gdelt_dim_coded_column_dictionary_pkey'),
    )

    column_name: Mapped[str] = mapped_column(Text, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    reference_table: Mapped[Optional[str]] = mapped_column(Text)


class GdeltDimGeoType(Base):
    __tablename__ = 'gdelt_dim_geo_type'
    __table_args__ = (
        PrimaryKeyConstraint('code', name='gdelt_dim_geo_type_pkey'),
    )

    code: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)


class GdeltDimQuadClass(Base):
    __tablename__ = 'gdelt_dim_quad_class'
    __table_args__ = (
        PrimaryKeyConstraint('code', name='gdelt_dim_quad_class_pkey'),
    )

    code: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)


t_gdelt_events_title_source_date = Table(
    'gdelt_events_title_source_date', Base.metadata,
    Column('sourceurl', Text),
    Column('title', Text),
    Column('sqldate', BigInteger)
)


t_news_count = Table(
    'news_count', Base.metadata,
    Column('count', BigInteger)
)


class ProcessedFiles(Base):
    __tablename__ = 'processed_files'
    __table_args__ = (
        PrimaryKeyConstraint('file_name', name='processed_files_pkey'),
    )

    file_name: Mapped[str] = mapped_column(Text, primary_key=True)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    processed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)


class G1Articles(Base):
    __tablename__ = 'g1_articles'
    __table_args__ = (
        ForeignKeyConstraint(['sitemap_url'], ['g1_sitemaps.sitemap_url'], ondelete='SET NULL', name='g1_articles_sitemap_url_fkey'),
        PrimaryKeyConstraint('url', name='g1_articles_pkey'),
        Index('idx_g1_articles_fetch_status', 'fetch_status'),
        Index('idx_g1_articles_last_seen', 'last_seen_at')
    )

    url: Mapped[str] = mapped_column(Text, primary_key=True)
    first_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    last_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    fetch_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    is_chunked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    sitemap_url: Mapped[Optional[str]] = mapped_column(Text)
    sitemap_lastmod: Mapped[Optional[str]] = mapped_column(Text)
    sitemap_article_lastmod: Mapped[Optional[str]] = mapped_column(Text)
    sitemap_image_url: Mapped[Optional[str]] = mapped_column(Text)
    fetch_status: Mapped[Optional[str]] = mapped_column(Text)
    fetch_error: Mapped[Optional[str]] = mapped_column(Text)
    http_status: Mapped[Optional[int]] = mapped_column(Integer)
    fetched_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    final_url: Mapped[Optional[str]] = mapped_column(Text)
    extraction_status: Mapped[Optional[str]] = mapped_column(Text)
    extraction_error: Mapped[Optional[str]] = mapped_column(Text)
    extracted_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    title: Mapped[Optional[str]] = mapped_column(Text)
    author: Mapped[Optional[str]] = mapped_column(Text)
    hostname: Mapped[Optional[str]] = mapped_column(Text)
    sitename: Mapped[Optional[str]] = mapped_column(Text)
    date_published: Mapped[Optional[datetime.date]] = mapped_column(Date)
    language: Mapped[Optional[str]] = mapped_column(Text)
    excerpt: Mapped[Optional[str]] = mapped_column(Text)
    categories: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text()))
    tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text()))
    text_content: Mapped[Optional[str]] = mapped_column(Text)
    raw_sitemap: Mapped[Optional[dict]] = mapped_column(JSONB)
    raw_metadata: Mapped[Optional[dict]] = mapped_column(JSONB)

    g1_sitemaps: Mapped[Optional['G1Sitemaps']] = relationship('G1Sitemaps', back_populates='g1_articles')
    g1_chunks: Mapped[list['G1Chunks']] = relationship('G1Chunks', back_populates='g1_articles')


class G1Chunks(Base):
    __tablename__ = 'g1_chunks'
    __table_args__ = (
        ForeignKeyConstraint(['article'], ['g1_articles.url'], name='fk_g1_chunks_g1_article'),
        PrimaryKeyConstraint('id', name='g1_chunks_pkey'),
        Index('g1_chunks_embedding_idx', 'embedding', postgresql_ops={'embedding': 'vector_cosine_ops'}, postgresql_using='hnsw')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    article: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[Any]] = mapped_column(VECTOR(768))
    chunk: Mapped[Optional[str]] = mapped_column(Text)

    g1_articles: Mapped['G1Articles'] = relationship('G1Articles', back_populates='g1_chunks')
