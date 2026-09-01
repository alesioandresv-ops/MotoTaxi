import 'dart:async';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import '../../app/theme.dart';
import '../../core/services/location_service.dart';
import '../../core/services/driver_service.dart';
import '../../core/services/trip_service.dart';
import '../../core/models/trip.dart';

class DriverHomeScreen extends StatefulWidget {
  const DriverHomeScreen({super.key});
  @override
  State<DriverHomeScreen> createState() => _DriverHomeScreenState();
}

class _DriverHomeScreenState extends State<DriverHomeScreen> {
  final _locationService = LocationService();
  final _driverService = DriverService();
  final _tripService = TripService();
  GoogleMapController? _mapController;
  bool _isOnline = false;
  bool _loading = true;
  StreamSubscription? _positionSub;
  List<Trip> _availableTrips = [];

  @override
  void initState() {
    super.initState();
    _init();
  }

  @override
  void dispose() {
    _positionSub?.cancel();
    super.dispose();
  }

  Future<void> _init() async {
    final pos = await _locationService.getCurrentPosition();
    if (mounted) {
      setState(() => _loading = false);
      if (pos != null) {
        _mapController?.animateCamera(
          CameraUpdate.newLatLngZoom(
            LatLng(pos.latitude, pos.longitude),
            15,
          ),
        );
      }
    }
  }

  Future<void> _toggleOnline() async {
    final newState = await _driverService.setOnline(isOnline: !_isOnline);
    if (mounted) {
      setState(() => _isOnline = newState);
      if (_isOnline) {
        _startLocationUpdates();
        _loadAvailableTrips();
      } else {
        _positionSub?.cancel();
        setState(() => _availableTrips = []);
      }
    }
  }

  void _startLocationUpdates() {
    _positionSub = _locationService.getPositionStream().listen((pos) {
      _driverService.updateLocation(lat: pos.latitude, lng: pos.longitude);
    });
  }

  Future<void> _loadAvailableTrips() async {
    final pos = await _locationService.getCurrentPosition();
    if (pos == null) return;
    final trips = await _tripService.getAvailableTrips(
      lat: pos.latitude,
      lng: pos.longitude,
    );
    if (mounted) setState(() => _availableTrips = trips);
  }

  Future<void> _acceptTrip(int tripId) async {
    await _tripService.acceptTrip(tripId);
    if (mounted) context.push('/driver/trip/$tripId');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Stack(
              children: [
                GoogleMap(
                  initialCameraPosition: const CameraPosition(
                    target: LatLng(-34.6037, -58.3816),
                    zoom: 15,
                  ),
                  onMapCreated: (c) => _mapController = c,
                  myLocationEnabled: true,
                  zoomControlsEnabled: false,
                ),
                Positioned(
                  top: MediaQuery.of(context).padding.top + 16,
                  left: 16,
                  right: 16,
                  child: _buildOnlineToggle(),
                ),
                Positioned(
                  bottom: 0,
                  left: 0,
                  right: 0,
                  child: _buildBottomPanel(),
                ),
              ],
            ),
    );
  }

  Widget _buildOnlineToggle() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(30),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.1),
            blurRadius: 8,
          ),
        ],
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            _isOnline ? 'En línea' : 'Fuera de línea',
            style: TextStyle(
              fontWeight: FontWeight.bold,
              color: _isOnline ? AppTheme.success : AppTheme.textSecondary,
            ),
          ),
          Switch(
            value: _isOnline,
            onChanged: (_) => _toggleOnline(),
            activeColor: AppTheme.success,
          ),
        ],
      ),
    );
  }

  Widget _buildBottomPanel() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.1),
            blurRadius: 10,
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (_isOnline && _availableTrips.isNotEmpty) ...[
            Text(
              '${_availableTrips.length} viajes disponibles',
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),
            ..._availableTrips.take(3).map((trip) => _buildTripCard(trip)),
          ] else if (_isOnline) ...[
            const Center(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: Text('Esperando viajes...',
                    style: TextStyle(color: AppTheme.textSecondary)),
              ),
            ),
          ] else ...[
            const Center(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: Text('Activá tu estado para recibir viajes',
                    style: TextStyle(color: AppTheme.textSecondary)),
              ),
            ),
          ],
          const SizedBox(height: 8),
          OutlinedButton(
            onPressed: _isOnline ? _loadAvailableTrips : null,
            child: const Text('Actualizar'),
          ),
        ],
      ),
    );
  }

  Widget _buildTripCard(Trip trip) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  trip.vehicleType == 'moto' ? Icons.two_wheeler : Icons.directions_car,
                  size: 20,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    trip.pickupAddress ?? 'Origen',
                    style: const TextStyle(fontWeight: FontWeight.w500),
                  ),
                ),
                if (trip.fare != null)
                  Text(
                    '\$${trip.fare!.toStringAsFixed(0)}',
                    style: const TextStyle(
                        fontWeight: FontWeight.bold, color: AppTheme.primary),
                  ),
              ],
            ),
            const SizedBox(height: 4),
            Row(
              children: [
                const Icon(Icons.arrow_downward,
                    size: 14, color: AppTheme.textSecondary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    trip.dropoffAddress ?? 'Destino',
                    style: TextStyle(
                        fontSize: 13, color: AppTheme.textSecondary),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () => _acceptTrip(trip.id),
                style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.success),
                child: const Text('Aceptar Viaje'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
