"""
Tests de tarifas y comisión (Fase 4 preparada): Decimal siempre,
invariante total_fare = platform_fee + driver_earnings.
"""
from decimal import Decimal

import pytest

from backend.services.fare import (
    build_fare, calcular_tarifa_real, round_money, as_decimal, commission_rate,
)


class TestFareBasics:
    def test_fare_is_decimal(self):
        fare = calcular_tarifa_real(5.0, 0, 'moto')
        assert isinstance(fare, Decimal)
        assert fare == Decimal('10.50')

    def test_fare_respects_minimum_moto(self):
        assert calcular_tarifa_real(0.1, 0, 'moto') == Decimal('5.00')

    def test_fare_respects_minimum_auto(self):
        assert calcular_tarifa_real(0.1, 0, 'auto') == Decimal('7.00')

    def test_fare_auto_higher_than_moto(self):
        auto = calcular_tarifa_real(10.0, 15, 'auto')
        moto = calcular_tarifa_real(10.0, 15, 'moto')
        assert auto > moto


class TestBuildFareNoCommission:
    def test_no_rate_gives_zero_fee(self, monkeypatch):
        monkeypatch.delenv('PLATFORM_FEE_RATE', raising=False)
        f = build_fare(5.0, 0, 'moto')
        assert f['platform_fee'] == Decimal('0')
        assert f['platform_fee_rate'] is None
        assert f['driver_earnings'] == f['total_fare']
        assert f['currency'] == 'ARS'

    def test_invariant_no_commission(self, monkeypatch):
        monkeypatch.delenv('PLATFORM_FEE_RATE', raising=False)
        f = build_fare(3.0, 10, 'moto')
        assert f['total_fare'] == f['platform_fee'] + f['driver_earnings']


class TestBuildFareCommission:
    def test_five_percent_rate(self, monkeypatch):
        monkeypatch.setenv('PLATFORM_FEE_RATE', '0.05')
        f = build_fare(5.0, 0, 'moto')  # total 10.50 → fee 0.53 (redondeo)
        assert f['platform_fee_rate'] == Decimal('0.05')
        assert f['platform_fee'] == Decimal('0.53')
        assert f['driver_earnings'] == Decimal('9.97')
        assert f['total_fare'] == f['platform_fee'] + f['driver_earnings']

    def test_zero_rate_treated_as_no_commission(self, monkeypatch):
        monkeypatch.setenv('PLATFORM_FEE_RATE', '0.00')
        f = build_fare(5.0, 0, 'moto')
        assert f['platform_fee'] == Decimal('0')
        assert f['platform_fee_rate'] is None
        assert f['driver_earnings'] == f['total_fare']

    def test_invalid_rate_falls_back_to_none(self, monkeypatch):
        monkeypatch.setenv('PLATFORM_FEE_RATE', 'abc')
        assert commission_rate() is None

    def test_invariant_with_commission(self, monkeypatch):
        monkeypatch.setenv('PLATFORM_FEE_RATE', '0.10')
        f = build_fare(7.0, 5, 'moto')
        assert f['total_fare'] == f['platform_fee'] + f['driver_earnings']
        assert f['platform_fee'] > 0
        assert f['driver_earnings'] < f['total_fare']


class TestDecimalHelpers:
    def test_as_decimal_from_float_no_precision_loss(self):
        assert as_decimal(0.1) + as_decimal(0.2) == Decimal('0.3')

    def test_as_decimal_none_is_zero(self):
        assert as_decimal(None) == Decimal('0')

    def test_round_money(self):
        assert round_money(Decimal('10.555')) == Decimal('10.56')
