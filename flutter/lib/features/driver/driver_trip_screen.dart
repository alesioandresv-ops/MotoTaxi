import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../app/theme.dart';
import '../../core/services/trip_service.dart';
import '../../core/models/trip.dart';

class DriverTripScreen extends StatefulWidget {
  final int tripId;
  const DriverTripScreen({super.key, required this.tripId});
  @override
  State<DriverTripScreen> createState() => _DriverTripScreenState();
}

class _DriverTripScreenState extends State<DriverTripScreen> {
  final _tripService = TripService();
  Trip? _trip;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadTrip();
  }

  Future<void> _loadTrip() async {
    final trip = await _tripService.getTrip(widget.tripId);
    if (mounted) {
      setState(() {
        _trip = trip;
        _loading = false;
      });
    }
  }

  Future<void> _startTrip() async {
    await _tripService.startTrip(widget.tripId);
    await _loadTrip();
  }

  Future<void> _completeTrip() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Finalizar Viaje'),
        content: const Text('¿Confirmás que querés finalizar?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancelar'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Finalizar'),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      await _tripService.completeTrip(widget.tripId);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Viaje completado')),
        );
        context.pop();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Viaje')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _trip == null
              ? const Center(child: Text('Viaje no encontrado'))
              : SingleChildScrollView(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _buildStatusBadge(),
                      const SizedBox(height: 20),
                      _buildAddressCard('Origen', _trip!.pickupAddress,
                          Icons.circle, AppTheme.success),
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 8),
                        child: Icon(Icons.arrow_downward,
                            color: AppTheme.textSecondary),
                      ),
                      _buildAddressCard('Destino', _trip!.dropoffAddress,
                          Icons.location_on, AppTheme.accent),
                      const SizedBox(height: 20),
                      if (_trip!.fare != null)
                        Container(
                          padding: const EdgeInsets.all(16),
                          decoration: BoxDecoration(
                            color: AppTheme.surface,
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              const Text('Tarifa'),
                              Text(
                                '\$${_trip!.fare!.toStringAsFixed(0)}',
                                style: const TextStyle(
                                  fontSize: 24,
                                  fontWeight: FontWeight.bold,
                                  color: AppTheme.primary,
                                ),
                              ),
                            ],
                          ),
                        ),
                      const SizedBox(height: 24),
                      if (_trip!.status == 'accepted')
                        ElevatedButton(
                          onPressed: _startTrip,
                          child: const Text('Iniciar Viaje'),
                        ),
                      if (_trip!.status == 'ongoing')
                        ElevatedButton(
                          onPressed: _completeTrip,
                          style: ElevatedButton.styleFrom(
                              backgroundColor: AppTheme.success),
                          child: const Text('Finalizar Viaje'),
                        ),
                      if (_trip!.status == 'requested')
                        const Center(
                          child: Padding(
                            padding: EdgeInsets.all(16),
                            child: Text('Esperando confirmación del pasajero...'),
                          ),
                        ),
                    ],
                  ),
                ),
    );
  }

  Widget _buildStatusBadge() {
    final color = _trip!.status == 'ongoing'
        ? AppTheme.success
        : _trip!.status == 'accepted'
            ? AppTheme.warning
            : AppTheme.primary;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        _statusLabel(),
        textAlign: TextAlign.center,
        style: TextStyle(
          color: color,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }

  Widget _buildAddressCard(
      String title, String? address, IconData icon, Color color) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppTheme.surface,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Icon(icon, color: color, size: 16),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: const TextStyle(
                        fontSize: 12, color: AppTheme.textSecondary)),
                Text(address ?? 'Sin dirección',
                    style: const TextStyle(fontWeight: FontWeight.w500)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _statusLabel() {
    switch (_trip?.status) {
      case 'requested':
        return 'Esperando';
      case 'accepted':
        return 'En camino al pasajero';
      case 'ongoing':
        return 'En viaje';
      case 'completed':
        return 'Completado';
      case 'cancelled':
        return 'Cancelado';
      default:
        return '';
    }
  }
}
