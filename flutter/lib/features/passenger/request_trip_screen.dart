import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import '../../app/theme.dart';
import '../../core/services/trip_service.dart';
import '../../core/services/location_service.dart';
import '../../core/services/driver_service.dart';
import '../../core/models/driver.dart';

class RequestTripScreen extends StatefulWidget {
  const RequestTripScreen({super.key});
  @override
  State<RequestTripScreen> createState() => _RequestTripScreenState();
}

class _RequestTripScreenState extends State<RequestTripScreen> {
  final _pickupCtrl = TextEditingController();
  final _dropoffCtrl = TextEditingController();
  final _tripService = TripService();
  final _locationService = LocationService();
  final _driverService = DriverService();
  String _vehicleType = 'moto';
  String _paymentMethod = 'efectivo';
  bool _loading = false;
  bool _searchingDrivers = false;
  List<DriverNearby> _nearbyDrivers = [];
  String? _error;

  LatLng? _pickupLatLng;
  LatLng? _dropoffLatLng;

  @override
  void dispose() {
    _pickupCtrl.dispose();
    _dropoffCtrl.dispose();
    super.dispose();
  }

  Future<void> _searchNearby() async {
    final pos = await _locationService.getCurrentPosition();
    if (pos == null) return;

    setState(() => _searchingDrivers = true);
    final drivers = await _driverService.getNearbyDrivers(
      lat: pos.latitude,
      lng: pos.longitude,
      vehicleType: _vehicleType,
    );
    if (mounted) {
      setState(() {
        _nearbyDrivers = drivers;
        _searchingDrivers = false;
      });
    }
  }

  Future<void> _requestTrip() async {
    if (_pickupCtrl.text.isEmpty || _dropoffCtrl.text.isEmpty) {
      setState(() => _error = 'Completá origen y destino');
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final idempotencyKey =
          DateTime.now().millisecondsSinceEpoch.toString();
      await _tripService.createTrip(
        pickupAddress: _pickupCtrl.text,
        dropoffAddress: _dropoffCtrl.text,
        vehicleType: _vehicleType,
        paymentMethod: _paymentMethod,
        idempotencyKey: idempotencyKey,
        pickupLat: _pickupLatLng?.latitude,
        pickupLng: _pickupLatLng?.longitude,
        dropoffLat: _dropoffLatLng?.latitude,
        dropoffLng: _dropoffLatLng?.longitude,
      );
      if (mounted) {
        context.push('/trip/active');
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Solicitar Viaje')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (_error != null)
              Container(
                margin: const EdgeInsets.only(bottom: 16),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppTheme.error.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(_error!,
                    style: const TextStyle(color: AppTheme.error)),
              ),
            TextField(
              controller: _pickupCtrl,
              decoration: const InputDecoration(
                labelText: 'Origen',
                prefixIcon: Icon(Icons.circle, color: AppTheme.success, size: 12),
                hintText: '¿Dónde estás?',
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _dropoffCtrl,
              decoration: const InputDecoration(
                labelText: 'Destino',
                prefixIcon: Icon(Icons.location_on, color: AppTheme.accent, size: 16),
                hintText: '¿A dónde vas?',
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 24),
            const Text('Tipo de vehículo',
                style: TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            Row(
              children: [
                _vehicleOption('moto', 'Moto', Icons.two_wheeler),
                const SizedBox(width: 12),
                _vehicleOption('auto', 'Auto', Icons.directions_car),
              ],
            ),
            const SizedBox(height: 24),
            const Text('Método de pago',
                style: TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _paymentOption('efectivo', 'Efectivo'),
                _paymentOption('mercadopago', 'Mercado Pago'),
                _paymentOption('transferencia', 'Transferencia'),
                _paymentOption('tarjeta', 'Tarjeta'),
                _paymentOption('billetera', 'Billetera VAN'),
              ],
            ),
            const SizedBox(height: 24),
            if (_nearbyDrivers.isNotEmpty)
              Container(
                margin: const EdgeInsets.only(bottom: 16),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppTheme.success.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  '${_nearbyDrivers.length} conductores disponibles cerca',
                  style: const TextStyle(color: AppTheme.success),
                ),
              ),
            ElevatedButton(
              onPressed: _loading ? null : _requestTrip,
              child: _loading
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : const Text('Solicitar Viaje'),
            ),
            const SizedBox(height: 8),
            TextButton(
              onPressed: _searchingDrivers ? null : _searchNearby,
              child: _searchingDrivers
                  ? const SizedBox(
                      height: 16,
                      width: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Buscar conductores cercanos'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _vehicleOption(String value, String label, IconData icon) {
    final selected = _vehicleType == value;
    return Expanded(
      child: GestureDetector(
        onTap: () => setState(() => _vehicleType = value),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(
            color: selected ? AppTheme.primary : Colors.white,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: selected ? AppTheme.primary : AppTheme.border,
            ),
          ),
          child: Column(
            children: [
              Icon(icon, color: selected ? Colors.white : AppTheme.primary),
              const SizedBox(height: 4),
              Text(
                label,
                style: TextStyle(
                  color: selected ? Colors.white : AppTheme.primary,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _paymentOption(String value, String label) {
    final selected = _paymentMethod == value;
    return ChoiceChip(
      label: Text(label),
      selected: selected,
      onSelected: (_) => setState(() => _paymentMethod = value),
      selectedColor: AppTheme.primary,
      labelStyle: TextStyle(
        color: selected ? Colors.white : AppTheme.textPrimary,
      ),
    );
  }
}
