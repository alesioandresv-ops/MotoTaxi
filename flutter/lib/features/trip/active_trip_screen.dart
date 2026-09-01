import 'dart:async';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import '../../app/theme.dart';
import '../../core/services/trip_service.dart';
import '../../core/models/trip.dart';

class ActiveTripScreen extends StatefulWidget {
  const ActiveTripScreen({super.key});
  @override
  State<ActiveTripScreen> createState() => _ActiveTripScreenState();
}

class _ActiveTripScreenState extends State<ActiveTripScreen> {
  final _tripService = TripService();
  GoogleMapController? _mapController;
  Trip? _trip;
  TripStatusUpdate? _status;
  Timer? _pollTimer;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadTrip();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadTrip() async {
    try {
      final trips = await _tripService.listTrips(status: 'requested');
      if (trips.isEmpty) {
        final ongoing = await _tripService.listTrips(status: 'ongoing');
        if (ongoing.isEmpty) {
          if (mounted) {
            setState(() {
              _error = 'No hay viaje activo';
              _loading = false;
            });
          }
          return;
        }
        _trip = ongoing.first;
      } else {
        _trip = trips.first;
      }

      if (mounted) {
        setState(() => _loading = false);
        _startPolling();
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

  void _startPolling() {
    _pollTimer = Timer.periodic(const Duration(seconds: 5), (_) => _pollStatus());
    _pollStatus();
  }

  Future<void> _pollStatus() async {
    if (_trip == null) return;
    try {
      final status = await _tripService.getTripStatus(_trip!.id);
      if (mounted) {
        setState(() => _status = status);

        if (status.status == 'completed' || status.status == 'cancelled') {
          _pollTimer?.cancel();
          if (status.status == 'completed') {
            context.push('/trip/rate/${_trip!.id}');
          } else {
            context.pop();
          }
        }
      }
    } catch (_) {}
  }

  Future<void> _cancelTrip() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cancelar viaje'),
        content: const Text('¿Estás seguro?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('No')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Sí', style: TextStyle(color: AppTheme.error)),
          ),
        ],
      ),
    );

    if (confirmed == true && _trip != null) {
      await _tripService.cancelTrip(_trip!.id);
      if (mounted) context.pop();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_statusLabel()),
        actions: [
          if (_trip?.canBeCancelled == true)
            IconButton(
              icon: const Icon(Icons.close),
              onPressed: _cancelTrip,
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(_error!),
                      const SizedBox(height: 16),
                      ElevatedButton(
                        onPressed: () => context.pop(),
                        child: const Text('Volver'),
                      ),
                    ],
                  ),
                )
              : Stack(
                  children: [
                    GoogleMap(
                      initialCameraPosition: CameraPosition(
                        target: LatLng(
                          _trip?.pickupLat ?? -34.6037,
                          _trip?.pickupLng ?? -58.3816,
                        ),
                        zoom: 15,
                      ),
                      onMapCreated: (c) => _mapController = c,
                      markers: _buildMarkers(),
                      myLocationEnabled: true,
                      zoomControlsEnabled: false,
                    ),
                    Positioned(
                      bottom: 0,
                      left: 0,
                      right: 0,
                      child: _buildInfoPanel(),
                    ),
                  ],
                ),
    );
  }

  Set<Marker> _buildMarkers() {
    final markers = <Marker>{};
    if (_trip?.pickupLat != null && _trip?.pickupLng != null) {
      markers.add(Marker(
        markerId: const MarkerId('pickup'),
        position: LatLng(_trip!.pickupLat!, _trip!.pickupLng!),
        infoWindow: InfoWindow(title: 'Origen'),
        icon: BitmapDescriptor.defaultMarkerWithHue(
            BitmapDescriptor.hueGreen),
      ));
    }
    if (_trip?.dropoffLat != null && _trip?.dropoffLng != null) {
      markers.add(Marker(
        markerId: const MarkerId('dropoff'),
        position: LatLng(_trip!.dropoffLat!, _trip!.dropoffLng!),
        infoWindow: InfoWindow(title: 'Destino'),
        icon: BitmapDescriptor.defaultMarkerWithHue(
            BitmapDescriptor.hueRed),
      ));
    }
    if (_status?.driverLat != null && _status?.driverLng != null) {
      markers.add(Marker(
        markerId: const MarkerId('driver'),
        position: LatLng(_status!.driverLat!, _status!.driverLng!),
        infoWindow: InfoWindow(
          title: _status?.driver?.name ?? 'Conductor',
        ),
        icon: BitmapDescriptor.defaultMarkerWithHue(
            BitmapDescriptor.hueBlue),
      ));
    }
    return markers;
  }

  Widget _buildInfoPanel() {
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
          if (_status?.driver != null) ...[
            Row(
              children: [
                CircleAvatar(
                  radius: 24,
                  backgroundColor: AppTheme.surface,
                  child: Text(
                    _status!.driver!.name.substring(0, 1).toUpperCase(),
                    style: const TextStyle(
                        fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        _status!.driver!.name,
                        style: const TextStyle(fontWeight: FontWeight.bold),
                      ),
                      if (_status!.driver!.vehicleInfo != null)
                        Text(
                          '${_status!.driver!.vehicleInfo!.marca} ${_status!.driver!.vehicleInfo!.modelo}',
                          style: TextStyle(
                              color: AppTheme.textSecondary, fontSize: 13),
                        ),
                    ],
                  ),
                ),
                if (_status!.driver!.ratingAvg > 0)
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: AppTheme.warning.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.star, size: 14, color: AppTheme.warning),
                        const SizedBox(width: 4),
                        Text(
                          _status!.driver!.ratingAvg.toStringAsFixed(1),
                          style: const TextStyle(fontWeight: FontWeight.bold),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 16),
          ],
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppTheme.surface,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              children: [
                const Icon(Icons.circle, color: AppTheme.success, size: 8),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(_trip?.pickupAddress ?? 'Origen',
                      style: const TextStyle(fontSize: 13)),
                ),
              ],
            ),
          ),
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 4),
            child: Icon(Icons.arrow_downward, size: 16, color: AppTheme.textSecondary),
          ),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppTheme.surface,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              children: [
                const Icon(Icons.location_on, color: AppTheme.accent, size: 16),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(_trip?.dropoffAddress ?? 'Destino',
                      style: const TextStyle(fontSize: 13)),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          if (_trip?.fare != null)
            Text(
              'Tarifa: \$${_trip!.fare!.toStringAsFixed(0)}',
              textAlign: TextAlign.center,
              style: const TextStyle(
                  fontSize: 18, fontWeight: FontWeight.bold),
            ),
          const SizedBox(height: 12),
          ElevatedButton(
            onPressed: _status?.status == 'ongoing' ? null : null,
            style: ElevatedButton.styleFrom(
              backgroundColor: AppTheme.textSecondary,
            ),
            child: Text(_statusLabel()),
          ),
        ],
      ),
    );
  }

  String _statusLabel() {
    switch (_status?.status ?? _trip?.status) {
      case 'requested':
        return 'Buscando conductor...';
      case 'accepted':
        return 'Conductor en camino';
      case 'ongoing':
        return 'En viaje';
      case 'completed':
        return 'Viaje completado';
      case 'cancelled':
        return 'Viaje cancelado';
      default:
        return 'Estado desconocido';
    }
  }
}
