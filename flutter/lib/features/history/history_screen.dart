import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../app/theme.dart';
import '../../core/services/trip_service.dart';
import '../../core/models/trip.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});
  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  final _tripService = TripService();
  List<Trip> _trips = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadHistory();
  }

  Future<void> _loadHistory() async {
    final completed = await _tripService.listTrips(status: 'completed');
    final cancelled = await _tripService.listTrips(status: 'cancelled');
    if (mounted) {
      setState(() {
        _trips = [...completed, ...cancelled];
        _trips.sort((a, b) =>
            (b.createdAt ?? DateTime(0)).compareTo(a.createdAt ?? DateTime(0)));
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Historial')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _trips.isEmpty
              ? const Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.history, size: 64, color: AppTheme.textSecondary),
                      SizedBox(height: 16),
                      Text('Sin viajes',
                          style: TextStyle(color: AppTheme.textSecondary)),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _loadHistory,
                  child: ListView.builder(
                    padding: const EdgeInsets.all(12),
                    itemCount: _trips.length,
                    itemBuilder: (_, i) => _buildTripCard(_trips[i]),
                  ),
                ),
    );
  }

  Widget _buildTripCard(Trip trip) {
    final isCompleted = trip.status == 'completed';
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: isCompleted
              ? AppTheme.success.withOpacity(0.1)
              : AppTheme.error.withOpacity(0.1),
          child: Icon(
            isCompleted ? Icons.check : Icons.close,
            color: isCompleted ? AppTheme.success : AppTheme.error,
          ),
        ),
        title: Text(
          trip.dropoffAddress ?? 'Sin destino',
          style: const TextStyle(fontWeight: FontWeight.w500),
        ),
        subtitle: Text(
          '${trip.pickupAddress ?? ''} → ${trip.dropoffAddress ?? ''}',
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 12),
        ),
        trailing: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            if (trip.fare != null)
              Text(
                '\$${trip.fare!.toStringAsFixed(0)}',
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
            Text(
              trip.createdAt != null
                  ? '${trip.createdAt!.day}/${trip.createdAt!.month}'
                  : '',
              style: const TextStyle(fontSize: 11, color: AppTheme.textSecondary),
            ),
          ],
        ),
      ),
    );
  }
}
