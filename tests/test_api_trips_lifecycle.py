"""Etapa 3 — Ciclo de vida de trips API v1 (contrato §§4.2, 5.2, 6, 12).

Cubre: detalle/listado/disponibles, accept (claim atómico y carrera),
reject/start/complete (cobro vía finalize_trip, método real del conductor,
billetera con y sin saldo, retry idempotente)/cancel/rate/eta y la matriz
de errores de la máquina de estados §6.
"""
import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal


REGISTER_PAX = {
    'name': 'Ana Pérez',
    'password': 'Pass1234',
    'phone': '3001112233',
}

REGISTER_DRIVER = {
    'name': 'Carlos Ruiz',
    'password': 'Pass1234',
    'phone': '3004445566',
    'vehicle_type': 'moto',
    'placa': 'ABC123',
    'moto_marca': 'Yamaha',
    'moto_modelo': 'R3',
    'moto_color': 'Rojo',
    'moto_cilindrada': '321',
    'tipo_seguro': 'Responsabilidad civil',
    'carnet_conducir': 'A1234567',
    'ultimo_servicio': '2026-07-01',
}

# Coordenadas CABA fijas: ningún test llama a Nominatim.
BASE_TRIP = {
    'pickup_address': 'Av Siempre Viva 742',
    'dropoff_address': 'Calle Falsa 123',
    'pickup_lat': -34.60,
    'pickup_lng': -58.38,
    'dropoff_lat': -34.62,
    'dropoff_lng': -58.40,
    'vehicle_type': 'moto',
    'payment_method': 'efectivo',
}


def _api(client, method, path, token=None, data=None, headers=None):
    hdrs = dict(headers or {})
    if token:
        hdrs['Authorization'] = f'Bearer {token}'
    return client.open(
        path, method=method, headers=hdrs,
        data=json.dumps(data) if data is not None else None,
        content_type='application/json',
    )


def _uniq(prefix):
    return f'{prefix}-{uuid.uuid4().hex[:8]}@test.com'


def _register_pax(client):
    email = _uniq('ana')
    rv = _api(client, 'POST', '/api/v1/auth/register',
              data=dict(REGISTER_PAX, email=email))
    assert rv.status_code == 201, rv.get_json()
    return email, rv.get_json()['data']['tokens']['access_token']


def _register_driver(app, client, approve=True, online=True, lat=-34.59, lng=-58.39):
    email = _uniq('carlos')
    rv = _api(client, 'POST', '/api/v1/auth/register/driver',
              data=dict(REGISTER_DRIVER, email=email))
    assert rv.status_code == 201, rv.get_json()
    token = rv.get_json()['data']['tokens']['access_token']
    return email, token, _setup_profile(app, email, approve=approve, online=online,
                                        lat=lat, lng=lng)


def _setup_profile(app, email, approve=True, online=True, lat=-34.59, lng=-58.39):
    """Aprueba el perfil (los registros nuevos nacen pending), setea estado."""
    from backend.models import db, User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        profile = user.driver_profile
        if approve:
            profile.status = 'approved'
        profile.is_online = online
        profile.is_busy = False
        profile.lat = lat
        profile.lng = lng
        db.session.commit()
        return user.id


def _create_trip(client, pax_token, key=None, **overrides):
    key = key or str(uuid.uuid4())
    rv = _api(client, 'POST', '/api/v1/trips', token=pax_token,
              data=dict(BASE_TRIP, **overrides),
              headers={'Idempotency-Key': key})
    assert rv.status_code == 201, rv.get_json()
    return rv.get_json()['data']['trip']['id']


def _fund(app, email, amount):
    from backend.models import db, User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.balance = Decimal(str(amount))
        db.session.commit()


def _balances(app, *emails):
    from backend.models import User
    with app.app_context():
        return {
            e: str(User.query.filter_by(email=e).first().balance or 0)
            for e in emails
        }


def _profile_field(app, email, field):
    from backend.models import User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        return getattr(user.driver_profile, field)


# ═══════════════════════ Detalle / listado ═══════════════════════

class TestGetTrip:
    def test_requires_token(self, client):
        rv = _api(client, 'GET', '/api/v1/trips/999')
        assert rv.status_code == 401
        assert rv.get_json()['error']['code'] == 'MISSING_TOKEN'

    def test_not_found(self, client):
        _, pax = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/trips/99999', token=pax)
        assert rv.status_code == 404
        assert rv.get_json()['error']['code'] == 'NOT_FOUND'

    def test_passenger_vees_su_viaje(self, client):
        _, pax = _register_pax(client)
        trip_id = _create_trip(client, pax)
        rv = _api(client, 'GET', f'/api/v1/trips/{trip_id}', token=pax)
        assert rv.status_code == 200
        trip = rv.get_json()['data']['trip']
        assert trip['id'] == trip_id
        assert trip['status'] == 'requested'
        assert Decimal(trip['fare']['estimate']['total_fare']) > 0
        assert trip['fare']['final'] is None
        assert trip['wallet'] == {'charged': False, 'passenger_txn_id': None,
                                  'driver_txn_id': None}
        assert trip['driver'] is None

    def test_forbidden_para_ajeno(self, client):
        _, pax = _register_pax(client)
        trip_id = _create_trip(client, pax)
        _, other = _register_pax(client)
        rv = _api(client, 'GET', f'/api/v1/trips/{trip_id}', token=other)
        assert rv.status_code == 403
        assert rv.get_json()['error']['code'] == 'FORBIDDEN'

    def test_driver_asignado_ve_el_viaje(self, client, app):
        _, pax = _register_pax(client)
        d_email, drv, _ = _register_driver(app, client)
        trip_id = _create_trip(client, pax)
        assert _api(client, 'POST', f'/api/v1/trips/{trip_id}/accept',
                    token=drv, data={}).status_code == 200
        rv = _api(client, 'GET', f'/api/v1/trips/{trip_id}', token=drv)
        assert rv.status_code == 200
        trip = rv.get_json()['data']['trip']
        assert trip['status'] == 'accepted'
        assert trip['driver']['name'] == REGISTER_DRIVER['name']


class TestListTrips:
    def test_role_passenger_lista_sus_viajes(self, client):
        _, pax = _register_pax(client)
        t1 = _create_trip(client, pax)
        # Un pasajero no puede tener dos viajes activos: se cancela el 1º.
        assert _api(client, 'POST', f'/api/v1/trips/{t1}/cancel',
                    token=pax, data={}).status_code == 200
        t2 = _create_trip(client, pax)
        rv = _api(client, 'GET', '/api/v1/trips', token=pax)
        assert rv.status_code == 200
        body = rv.get_json()['data']
        ids = [t['id'] for t in body['items']]
        assert ids == [t2, t1]  # requested_at DESC
        pg = body['pagination']
        assert pg == {'page': 1, 'limit': 20, 'total': 2, 'pages': 1}

    def test_role_driver_lista_asignados(self, client, app):
        _, pax1 = _register_pax(client)
        _, pax2 = _register_pax(client)
        d_email, drv, _ = _register_driver(app, client)
        t1 = _create_trip(client, pax1)
        _create_trip(client, pax2)  # otro viaje que NO acepta
        assert _api(client, 'POST', f'/api/v1/trips/{t1}/accept',
                    token=drv, data={}).status_code == 200
        rv = _api(client, 'GET', '/api/v1/trips?role=driver', token=drv)
        assert rv.status_code == 200
        items = rv.get_json()['data']['items']
        assert [t['id'] for t in items] == [t1]

    def test_filtro_status(self, client, app):
        _, pax = _register_pax(client)
        t1 = _create_trip(client, pax)
        _api(client, 'POST', f'/api/v1/trips/{t1}/cancel', token=pax,
             data={'reason': 'nada'})
        _create_trip(client, pax)  # sigue requested
        rv = _api(client, 'GET', '/api/v1/trips?status=cancelled', token=pax)
        items = rv.get_json()['data']['items']
        assert len(items) == 1 and items[0]['status'] == 'cancelled'
        assert items[0]['cancelled_by'] == 'passenger'

    def test_status_invalido(self, client):
        _, pax = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/trips?status=virado', token=pax)
        assert rv.status_code == 400
        assert rv.get_json()['error']['code'] == 'VALIDATION_ERROR'

    def test_role_invalido(self, client):
        _, pax = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/trips?role=admin', token=pax)
        assert rv.status_code == 400

    def test_paginacion(self, client):
        _, pax = _register_pax(client)
        for i in range(3):
            trip_id = _create_trip(client, pax)
            if i < 2:  # deja el último activo; los previos cancelados cuentan igual
                _api(client, 'POST', f'/api/v1/trips/{trip_id}/cancel',
                     token=pax, data={})
        rv = _api(client, 'GET', '/api/v1/trips?page=2&limit=2', token=pax)
        body = rv.get_json()['data']
        assert len(body['items']) == 1
        assert body['pagination'] == {'page': 2, 'limit': 2, 'total': 3, 'pages': 2}


# ═══════════════════════ Disponibles (conductor) ═══════════════════════

class TestAvailableTrips:
    def test_requires_driver_mode(self, client):
        _, pax = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/trips/available'
                  '?lat=-34.6&lng=-58.4', token=pax)
        assert rv.status_code == 403  # rol pasajero puro

    def test_location_required_sin_posicion(self, client, app):
        _, drv, _ = _register_driver(app, client, lat=None, lng=None)
        rv = _api(client, 'GET', '/api/v1/trips/available', token=drv)
        assert rv.status_code == 400
        assert rv.get_json()['error']['code'] == 'LOCATION_REQUIRED'

    def test_usa_posicion_del_query(self, client, app):
        _, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client, lat=-34.61, lng=-58.39)
        trip_id = _create_trip(client, pax)
        # Query lejano (radio 10 km no alcanza): vacío pero sin LOCATION_REQUIRED.
        rv = _api(client, 'GET', '/api/v1/trips/available?lat=-38.0&lng=-57.5',
                  token=drv)
        assert rv.status_code == 200
        body = rv.get_json()['data']
        assert body['items'] == []
        assert body['pagination']['total'] == 0
        # Cerca: aparece ordenado con distancia al pickup.
        rv = _api(client, 'GET', '/api/v1/trips/available', token=drv)
        items = rv.get_json()['data']['items']
        assert [i['id'] for i in items] == [trip_id]
        item = items[0]
        assert item['pickup_address'] == BASE_TRIP['pickup_address']
        assert item['vehicle_type'] == 'moto'
        assert item['payment_method'] == 'efectivo'
        assert 0 < item['distance_km'] < 10  # dentro del radio default
        assert item['requested_at']
        assert item['fare']['estimate']['total_fare']

    def test_filtro_vehicle_type(self, client, app):
        _, pax = _register_pax(client)
        _, drv_auto, _ = _register_driver(app, client)
        _create_trip(client, pax, vehicle_type='auto')
        rv = _api(client, 'GET',
                  '/api/v1/trips/available?vehicle_type=moto', token=drv_auto)
        assert rv.get_json()['data']['items'] == []
        rv = _api(client, 'GET',
                  '/api/v1/trips/available?vehicle_type=auto', token=drv_auto)
        assert len(rv.get_json()['data']['items']) == 1

    def test_stale_requested_se_cancela_system(self, client, app):
        _, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client)
        trip_id = _create_trip(client, pax)
        from backend.models import db, Trip
        with app.app_context():
            trip = Trip.query.get(trip_id)
            trip.requested_at = datetime.utcnow() - timedelta(minutes=6)
            db.session.commit()
        rv = _api(client, 'GET', '/api/v1/trips/available', token=drv)
        assert rv.get_json()['data']['items'] == []
        rv = _api(client, 'GET', f'/api/v1/trips/{trip_id}', token=pax)
        trip = rv.get_json()['data']['trip']
        assert trip['status'] == 'cancelled'
        assert trip['cancelled_by'] == 'system'


# ═══════════════════════ Accept / reject ═══════════════════════

class TestAcceptTrip:
    def test_happy_path(self, client, app):
        _, pax = _register_pax(client)
        d_email, drv, _ = _register_driver(app, client)
        trip_id = _create_trip(client, pax)
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/accept',
                  token=drv, data={})
        assert rv.status_code == 200, rv.get_json()
        trip = rv.get_json()['data']['trip']
        assert trip['status'] == 'accepted'
        assert trip['driver']['name'] == REGISTER_DRIVER['name']
        assert _profile_field(app, d_email, 'is_busy') is True

    def test_carrera_dos_conductores_un_ganador(self, client, app):
        _, pax = _register_pax(client)
        _, drv1, _ = _register_driver(app, client, lat=-34.60, lng=-58.38)
        _, drv2, _ = _register_driver(app, client, lat=-34.61, lng=-58.39)
        trip_id = _create_trip(client, pax)
        r1 = _api(client, 'POST', f'/api/v1/trips/{trip_id}/accept',
                  token=drv1, data={})
        r2 = _api(client, 'POST', f'/api/v1/trips/{trip_id}/accept',
                  token=drv2, data={})
        codes = sorted([r1.status_code, r2.status_code])
        assert codes[0] == 200 and codes[1] == 409
        loser = r1 if r1.status_code == 409 else r2
        assert loser.get_json()['error']['code'] == 'TRIP_NOT_AVAILABLE'

    def test_offline_no_puede_aceptar(self, client, app):
        _, pax = _register_pax(client)
        d_email, drv, _ = _register_driver(app, client, online=False)
        trip_id = _create_trip(client, pax)
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/accept',
                  token=drv, data={})
        assert rv.status_code == 409
        assert rv.get_json()['error']['code'] == 'NOT_ONLINE'

    def test_ocupado_no_puede_aceptar_otro(self, client, app):
        _, pax1 = _register_pax(client)
        _, pax2 = _register_pax(client)
        d_email, drv, _ = _register_driver(app, client)
        t1 = _create_trip(client, pax1)
        assert _api(client, 'POST', f'/api/v1/trips/{t1}/accept',
                    token=drv, data={}).status_code == 200
        # Conductor ocupado intenta un viaje de OTRO pasajero.
        t2 = _create_trip(client, pax2)
        rv = _api(client, 'POST', f'/api/v1/trips/{t2}/accept',
                  token=drv, data={})
        assert rv.status_code == 409
        assert rv.get_json()['error']['code'] == 'TRIP_NOT_AVAILABLE'

    def test_pending_no_verificado(self, client, app):
        _, pax = _register_pax(client)
        _, drv_pending, _ = _register_driver(app, client, approve=False)
        trip_id = _create_trip(client, pax)
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/accept',
                  token=drv_pending, data={})
        assert rv.status_code == 403
        assert rv.get_json()['error']['code'] == 'NOT_VERIFIED'

    def test_not_found(self, client, app):
        _, drv, _ = _register_driver(app, client)
        rv = _api(client, 'POST', '/api/v1/trips/99999/accept',
                  token=drv, data={})
        assert rv.status_code == 404


class TestRejectTrip:
    def test_reject_sin_efecto(self, client, app):
        _, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client)
        trip_id = _create_trip(client, pax)
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/reject',
                  token=drv, data={})
        assert rv.status_code == 200
        assert rv.get_json()['data'] == {'ok': True}
        rv = _api(client, 'GET', f'/api/v1/trips/{trip_id}', token=pax)
        assert rv.get_json()['data']['trip']['status'] == 'requested'

    def test_reject_not_found(self, client, app):
        _, drv, _ = _register_driver(app, client)
        rv = _api(client, 'POST', '/api/v1/trips/99999/reject',
                  token=drv, data={})
        assert rv.status_code == 404

    def test_pasajero_forbidden(self, client):
        _, pax = _register_pax(client)
        rv = _api(client, 'POST', '/api/v1/trips/1/reject', token=pax, data={})
        assert rv.status_code == 403


# ═══════════════════════ Start ═══════════════════════

class TestStartTrip:
    def test_happy_path(self, client, app):
        _, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client)
        trip_id = _create_trip(client, pax)
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/accept', token=drv, data={})
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/start',
                  token=drv, data={})
        assert rv.status_code == 200
        trip = rv.get_json()['data']['trip']
        assert trip['status'] == 'ongoing'
        assert trip['started_at']

    def test_solo_asignado(self, client, app):
        _, pax = _register_pax(client)
        _, drv1, _ = _register_driver(app, client)
        _, drv2, _ = _register_driver(app, client)
        trip_id = _create_trip(client, pax)
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/accept', token=drv1, data={})
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/start',
                  token=drv2, data={})
        assert rv.status_code == 403
        assert rv.get_json()['error']['code'] == 'FORBIDDEN'

    def test_no_asignado_forbidden(self, client, app):
        """Un conductor que no fue asignado no puede iniciar (requested)."""
        _, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client)
        trip_id = _create_trip(client, pax)
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/start',
                  token=drv, data={})
        assert rv.status_code == 403
        assert rv.get_json()['error']['code'] == 'FORBIDDEN'

    def test_ya_ongoing_invalid_transition(self, client, app):
        _, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client)
        trip_id = _create_trip(client, pax)
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/accept', token=drv, data={})
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/start', token=drv, data={})
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/start',
                  token=drv, data={})
        assert rv.status_code == 409
        assert rv.get_json()['error']['code'] == 'INVALID_TRANSITION'


# ═══════════════════════ Complete (cobro) ═══════════════════════

def _to_ongoing(client, pax, drv, payment_method='efectivo'):
    trip_id = _create_trip(client, pax, payment_method=payment_method)
    _api(client, 'POST', f'/api/v1/trips/{trip_id}/accept', token=drv, data={})
    _api(client, 'POST', f'/api/v1/trips/{trip_id}/start', token=drv, data={})
    return trip_id


class TestCompleteTrip:
    def test_efectivo_happy_path(self, client, app, monkeypatch):
        monkeypatch.setenv('PLATFORM_FEE_RATE', '0.05')
        _, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client)
        trip_id = _to_ongoing(client, pax, drv)
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/complete',
                  token=drv, data={})
        assert rv.status_code == 200, rv.get_json()
        trip = rv.get_json()['data']['trip']
        assert trip['status'] == 'completed'
        assert trip['completed_at']
        assert trip['duration_min'] >= 1
        final = trip['fare']['final']
        assert final is not None and final['total_fare'] > '0'
        assert final['platform_fee_rate'] == '0.05'  # comisión activa por defecto
        # total = fee + earnings (invariante I1)
        assert Decimal(final['total_fare']) == (
            Decimal(final['platform_fee']) + Decimal(final['driver_earnings'])
        )
        assert trip['wallet']['charged'] is False  # efectivo no mueve saldo

    def test_metodo_real_del_conductor(self, client, app):
        """Paridad web: el conductor confirma cómo pagaron realmente."""
        _, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client)
        trip_id = _to_ongoing(client, pax, drv, payment_method='billetera')
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/complete',
                  token=drv, data={'method': 'efectivo'})
        assert rv.status_code == 200
        trip = rv.get_json()['data']['trip']
        assert trip['wallet']['charged'] is False
        rv = _api(client, 'GET', f'/api/v1/trips/{trip_id}', token=pax)
        # El método elegido por el pasajero se mantiene en el viaje;
        # el real confirmado vive en payment_method_collected.
        assert rv.get_json()['data']['trip']['payment_method'] == 'billetera'

    def test_billetera_con_saldo(self, client, app):
        pax_email, pax = _register_pax(client)
        d_email, drv, _ = _register_driver(app, client)
        trip_id = _to_ongoing(client, pax, drv, payment_method='billetera')
        _fund(app, pax_email, '100.00')
        before = _balances(app, pax_email, d_email)

        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/complete',
                  token=drv, data={})
        assert rv.status_code == 200
        trip = rv.get_json()['data']['trip']
        assert trip['wallet']['charged'] is True
        assert trip['wallet']['passenger_txn_id']
        assert trip['wallet']['driver_txn_id']

        total = Decimal(trip['fare']['final']['total_fare'])
        earnings = Decimal(trip['fare']['final']['driver_earnings'])
        after = _balances(app, pax_email, d_email)
        assert Decimal(after[pax_email]) == Decimal(before[pax_email]) - total
        assert Decimal(after[d_email]) == Decimal(before[d_email]) + earnings

    def test_billetera_sin_saldo_sigue_ongoing(self, client, app):
        _, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client)
        trip_id = _to_ongoing(client, pax, drv, payment_method='billetera')
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/complete',
                  token=drv, data={})
        assert rv.status_code == 400
        assert rv.get_json()['error']['code'] == 'INSUFFICIENT_BALANCE'
        rv = _api(client, 'GET', f'/api/v1/trips/{trip_id}', token=pax)
        assert rv.get_json()['data']['trip']['status'] == 'ongoing'

    def test_retry_idempotente(self, client, app):
        pax_email, pax = _register_pax(client)
        d_email, drv, _ = _register_driver(app, client)
        trip_id = _to_ongoing(client, pax, drv, payment_method='billetera')
        _fund(app, pax_email, '50.00')
        r1 = _api(client, 'POST', f'/api/v1/trips/{trip_id}/complete',
                  token=drv, data={})
        assert r1.status_code == 200
        r2 = _api(client, 'POST', f'/api/v1/trips/{trip_id}/complete',
                  token=drv, data={})
        assert r2.status_code == 200  # ya cobrado: resumen sin re-cobrar
        after = _balances(app, pax_email, d_email)
        total = Decimal(r1.get_json()['data']['trip']['fare']['final']['total_fare'])
        assert Decimal(after[pax_email]) == Decimal('50.00') - total  # un solo débito

    def test_desde_accepted_invalid_transition(self, client, app):
        _, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client)
        trip_id = _create_trip(client, pax)
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/accept', token=drv, data={})
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/complete',
                  token=drv, data={})
        assert rv.status_code == 409
        assert rv.get_json()['error']['code'] == 'INVALID_TRANSITION'

    def test_pasajero_forbidden(self, client, app):
        _, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client)
        trip_id = _to_ongoing(client, pax, drv)
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/complete',
                  token=pax, data={})
        assert rv.status_code == 403


# ═══════════════════════ Cancel ═══════════════════════

class TestCancelTrip:
    def test_pasajero_cancela_requested(self, client, app):
        _, pax = _register_pax(client)
        trip_id = _create_trip(client, pax)
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/cancel',
                  token=pax, data={'reason': 'cambio de planes'})
        assert rv.status_code == 200
        trip = rv.get_json()['data']['trip']
        assert trip['status'] == 'cancelled'
        assert trip['cancelled_by'] == 'passenger'

    def test_driver_asignado_cancela_y_libera_busy(self, client, app):
        _, pax = _register_pax(client)
        d_email, drv, _ = _register_driver(app, client)
        trip_id = _create_trip(client, pax)
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/accept', token=drv, data={})
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/cancel',
                  token=drv, data={'reason': 'imprevisto'})
        assert rv.status_code == 200
        trip = rv.get_json()['data']['trip']
        assert trip['status'] == 'cancelled'
        assert trip['cancelled_by'] == 'driver'
        assert _profile_field(app, d_email, 'is_busy') is False

    def test_completado_trip_finalized(self, client, app):
        _, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client)
        trip_id = _to_ongoing(client, pax, drv)
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/complete', token=drv, data={})
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/cancel',
                  token=pax, data={})
        assert rv.status_code == 409
        assert rv.get_json()['error']['code'] == 'TRIP_FINALIZED'

    def test_stranger_forbidden(self, client, app):
        _, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client)
        trip_id = _create_trip(client, pax)
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/cancel',
                  token=drv, data={})  # conductor SIN asignación
        assert rv.status_code == 403

    def test_reason_no_texto_validacion(self, client):
        _, pax = _register_pax(client)
        trip_id = _create_trip(client, pax)
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/cancel',
                  token=pax, data={'reason': 42})
        assert rv.status_code == 400


# ═══════════════════════ Rate ═══════════════════════

class TestRateTrip:
    def test_pasajero_califica_driver(self, client, app):
        _, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client)
        trip_id = _to_ongoing(client, pax, drv)
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/complete', token=drv, data={})
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/rate',
                  token=pax, data={'rating': 5, 'comment': 'Impecable'})
        assert rv.status_code == 200
        assert rv.get_json()['data']['ok'] is True

        from backend.models import User
        with app.app_context():
            driver = User.query.filter(
                User.email.like('carlos-%')).first()
            assert driver.rating_count == 1
            assert float(driver.rating_avg) == 5.0

    def test_driver_califica_passenger(self, client, app):
        pax_email, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client)
        trip_id = _to_ongoing(client, pax, drv)
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/complete', token=drv, data={})
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/rate',
                  token=drv, data={'rating': 4})
        assert rv.status_code == 200
        from backend.models import User
        with app.app_context():
            pax_user = User.query.filter_by(email=pax_email).first()
            assert pax_user.rating_count == 1
            assert float(pax_user.rating_avg) == 4.0

    def test_already_rated_por_rol(self, client, app):
        _, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client)
        trip_id = _to_ongoing(client, pax, drv)
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/complete', token=drv, data={})
        first = _api(client, 'POST', f'/api/v1/trips/{trip_id}/rate',
                     token=pax, data={'rating': 3})
        assert first.status_code == 200
        dup = _api(client, 'POST', f'/api/v1/trips/{trip_id}/rate',
                   token=pax, data={'rating': 5})
        assert dup.status_code == 409
        assert dup.get_json()['error']['code'] == 'ALREADY_RATED'

    def test_ratings_invalidos(self, client, app):
        _, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client)
        trip_id = _to_ongoing(client, pax, drv)
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/complete', token=drv, data={})
        for bad in (0, 6, 'x', 3.5, True, None):
            rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/rate',
                      token=pax, data={'rating': bad})
            assert rv.status_code == 400, bad
            assert rv.get_json()['error']['code'] == 'INVALID_RATING', bad

    def test_no_completed_trip_not_completed(self, client, app):
        _, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client)
        trip_id = _to_ongoing(client, pax, drv)  # ongoing, no completed
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/rate',
                  token=pax, data={'rating': 5})
        assert rv.status_code == 409
        assert rv.get_json()['error']['code'] == 'TRIP_NOT_COMPLETED'

    def test_stranger_forbidden(self, client, app):
        _, pax = _register_pax(client)
        _, other = _register_pax(client)
        _, drv, _ = _register_driver(app, client)
        trip_id = _to_ongoing(client, pax, drv)
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/complete', token=drv, data={})
        rv = _api(client, 'POST', f'/api/v1/trips/{trip_id}/rate',
                  token=other, data={'rating': 5})
        assert rv.status_code == 403


# ═══════════════════════ ETA ═══════════════════════

class TestTripEta:
    def test_con_conductor_ubicado(self, client, app):
        _, pax = _register_pax(client)
        _, drv, _ = _register_driver(app, client, lat=-34.60, lng=-58.38)
        trip_id = _create_trip(client, pax)
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/accept', token=drv, data={})
        rv = _api(client, 'GET', f'/api/v1/trips/{trip_id}/eta', token=pax)
        assert rv.status_code == 200
        eta = rv.get_json()['data']
        assert eta['distance_km'] == 0  # mismo punto que el pickup
        assert eta['eta_min'] >= 1
        assert eta['driver_lat'] == -34.60
        assert eta['driver_lng'] == -58.38

    def test_sin_conductor_nulls(self, client, app):
        _, pax = _register_pax(client)
        trip_id = _create_trip(client, pax)
        rv = _api(client, 'GET', f'/api/v1/trips/{trip_id}/eta', token=pax)
        assert rv.status_code == 200
        assert rv.get_json()['data'] == {
            'eta_min': None, 'distance_km': None,
            'driver_lat': None, 'driver_lng': None,
        }

    def test_not_found(self, client):
        _, pax = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/trips/99999/eta', token=pax)
        assert rv.status_code == 404

    def test_stranger_forbidden(self, client, app):
        _, pax = _register_pax(client)
        _, other = _register_pax(client)
        trip_id = _create_trip(client, pax)
        rv = _api(client, 'GET', f'/api/v1/trips/{trip_id}/eta', token=other)
        assert rv.status_code == 403


# ═══════════════════════ GET /trips/{id}/status (polling) ═══════════════════

class TestTripStatus:

    def test_status_returns_basic_fields(self, app, client):
        _, pax = _register_pax(client)
        _, drv_token, _ = _register_driver(app, client)
        trip_id = _create_trip(client, pax)
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/accept', token=drv_token)
        rv = _api(client, 'GET', f'/api/v1/trips/{trip_id}/status', token=pax)
        assert rv.status_code == 200
        data = rv.get_json()['data']
        assert data['id'] == trip_id
        assert data['status'] == 'accepted'
        assert 'pickup_address' in data
        assert 'dropoff_address' in data
        assert 'payment_method' in data

    def test_status_includes_driver_location(self, app, client):
        _, pax = _register_pax(client)
        _, drv_token, _ = _register_driver(app, client, lat=-34.59, lng=-58.39)
        trip_id = _create_trip(client, pax)
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/accept', token=drv_token)
        rv = _api(client, 'GET', f'/api/v1/trips/{trip_id}/status', token=pax)
        data = rv.get_json()['data']
        assert data['driver'] is not None
        assert data['driver']['lat'] == -34.59
        assert data['driver']['lng'] == -58.39

    def test_status_no_driver_before_accept(self, app, client):
        _, pax = _register_pax(client)
        trip_id = _create_trip(client, pax)
        rv = _api(client, 'GET', f'/api/v1/trips/{trip_id}/status', token=pax)
        data = rv.get_json()['data']
        assert data['status'] == 'requested'
        assert data['driver'] is None

    def test_status_includes_payment_fields(self, app, client):
        _, pax = _register_pax(client)
        _, drv_token, _ = _register_driver(app, client)
        trip_id = _create_trip(client, pax, payment_method='mercadopago')
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/accept', token=drv_token)
        rv = _api(client, 'GET', f'/api/v1/trips/{trip_id}/status', token=pax)
        data = rv.get_json()['data']
        assert data['payment_method'] == 'mercadopago'
        assert 'payment_status' in data

    def test_status_driver_can_access(self, app, client):
        _, pax = _register_pax(client)
        _, drv_token, _ = _register_driver(app, client)
        trip_id = _create_trip(client, pax)
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/accept', token=drv_token)
        rv = _api(client, 'GET', f'/api/v1/trips/{trip_id}/status', token=drv_token)
        assert rv.status_code == 200

    def test_status_stranger_forbidden(self, app, client):
        _, pax = _register_pax(client)
        _, other = _register_pax(client)
        trip_id = _create_trip(client, pax)
        rv = _api(client, 'GET', f'/api/v1/trips/{trip_id}/status', token=other)
        assert rv.status_code == 403

    def test_status_nonexistent_trip(self, app, client):
        _, pax = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/trips/99999/status', token=pax)
        assert rv.status_code == 404

    def test_status_unauthenticated(self, client):
        rv = _api(client, 'GET', '/api/v1/trips/1/status')
        assert rv.status_code == 401
