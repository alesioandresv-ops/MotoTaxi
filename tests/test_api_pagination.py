"""Etapa 0 — paginación común (contrato §13).

Cubre: default (1, 20); límite explícito; clamp del máximo (100);
valores inválidos (page < 1, limit < 1, no numéricos); estructura
`{items, pagination}`; orden estable y envuelta en el envelope.
"""
import uuid

import pytest

from backend.api.errors import ApiError
from backend.api.pagination import MAX_LIMIT, paginate, pagination_args
from backend.models import User, db


class TestPaginationArgs:
    def test_default(self):
        assert pagination_args({}) == (1, 20)
        assert pagination_args(None) == (1, 20)

    def test_explicitos(self):
        assert pagination_args({'page': '2', 'limit': '10'}) == (2, 10)

    def test_clamp_maximo(self):
        assert pagination_args({'limit': '150'}) == (1, MAX_LIMIT)
        assert pagination_args({'limit': '10000'}) == (1, MAX_LIMIT)

    def test_page_invalido(self):
        for bad in ('0', '-1', 'abc', '2.5', '1,5'):
            with pytest.raises(ApiError) as exc:
                pagination_args({'page': bad})
            assert exc.value.code == 'VALIDATION_ERROR'
            assert exc.value.status == 400

    def test_limit_invalido(self):
        for bad in ('0', '-5', 'x', '20.5'):
            with pytest.raises(ApiError) as exc:
                pagination_args({'limit': bad})
            assert exc.value.code == 'VALIDATION_ERROR'
            assert exc.value.status == 400


class TestPaginate:
    @pytest.fixture
    def users(self, app):
        with app.app_context():
            for i in range(25):
                db.session.add(User(
                    name=f'U{i}', email=f'u{i}-{uuid.uuid4().hex[:8]}@van.test',
                    password='x', role='passenger',
                ))
            db.session.commit()
        return app

    def _query(self, app):
        return User.query.order_by(User.created_at.desc(), User.id.desc())

    def test_estructura_y_slices(self, users):
        with users.app_context():
            page, limit = pagination_args({'page': '2', 'limit': '20'})
            out = paginate(self._query(users), page, limit)
        assert out['pagination'] == {'page': 2, 'limit': 20, 'total': 25, 'pages': 2}
        assert len(out['items']) == 5

    def test_pagina_1_default(self, users):
        with users.app_context():
            page, limit = pagination_args({})
            out = paginate(self._query(users), page, limit)
        assert out['pagination'] == {'page': 1, 'limit': 20, 'total': 25, 'pages': 2}
        assert len(out['items']) == 20

    def test_pagina_vacia(self, users):
        with users.app_context():
            page, limit = pagination_args({'page': '99'})
            out = paginate(self._query(users), page, limit)
        assert out['pagination']['total'] == 25
        assert out['items'] == []

    def test_sin_datos(self, app):
        with app.app_context():
            page, limit = pagination_args({})
            out = paginate(User.query, page, limit)
        assert out['pagination'] == {'page': 1, 'limit': 20, 'total': 0, 'pages': 0}
        assert out['items'] == []


class TestEnvelopeIntegration:
    def test_ruta_paginada_con_envelope(self, app):
        """Integración: el envelope devuelve {items, pagination} como data."""
        from backend.api import ok
        from backend.api.pagination import paginate, pagination_args
        from backend.api.serializers import public_user
        from backend.api.jwt import jwt_required

        with app.app_context():
            for i in range(5):
                db.session.add(User(
                    name=f'P{i}', email=f'p{i}-{uuid.uuid4().hex[:8]}@van.test',
                    password='x', role='passenger',
                ))
            db.session.commit()

        @app.route('/t/paginated')
        @jwt_required
        def t_paginated():
            page, limit = pagination_args()
            out = paginate(User.query.order_by(User.id.desc()), page, limit)
            return ok({
                'items': [public_user(u) for u in out['items']],
                'pagination': out['pagination'],
            })

        from backend.api.jwt import create_access_token
        with app.app_context():
            token = create_access_token(1, 'passenger', 'passenger')
        resp = app.test_client().get('/t/paginated',
                                     headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert body['data']['pagination'] == {'page': 1, 'limit': 20, 'total': 5, 'pages': 1}
        assert len(body['data']['items']) == 5
        assert body['data']['items'][0]['rating_avg'] == 5.0
