import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../app/theme.dart';
import '../../core/api/api_client.dart';
import '../../core/services/auth_service.dart';
import '../../core/services/wallet_service.dart';
import '../../core/services/driver_service.dart';
import '../../core/models/user.dart';
import '../../core/models/wallet.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});
  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  final _authService = AuthService();
  final _walletService = WalletService();
  final _driverService = DriverService();
  User? _user;
  Wallet? _wallet;
  List<String> _acceptedPayments = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    final user = await _authService.getMe();
    final wallet = await _walletService.getWallet();
    List<String> payments = [];
    if (user.isDriver) {
      payments = await _driverService.getAcceptedPayments();
    }
    if (mounted) {
      setState(() {
        _user = user;
        _wallet = wallet;
        _acceptedPayments = payments;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Mi Perfil'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () async {
              await ApiClient.instance.logout();
              if (mounted) context.go('/login');
            },
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(20),
              children: [
                _buildAvatar(),
                const SizedBox(height: 20),
                _buildInfoSection(),
                const SizedBox(height: 20),
                if (_user!.isDriver) ...[
                  _buildDriverSection(),
                  const SizedBox(height: 20),
                ],
                _buildActionsSection(),
              ],
            ),
    );
  }

  Widget _buildAvatar() {
    return Center(
      child: CircleAvatar(
        radius: 50,
        backgroundColor: AppTheme.primary,
        child: Text(
          (_user?.name ?? 'U').substring(0, 1).toUpperCase(),
          style: const TextStyle(
              fontSize: 36, color: Colors.white, fontWeight: FontWeight.bold),
        ),
      ),
    );
  }

  Widget _buildInfoSection() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _infoRow('Nombre', _user?.name),
            const Divider(),
            _infoRow('Email', _user?.email),
            const Divider(),
            _infoRow('Teléfono', _user?.phone ?? 'No registrado'),
            const Divider(),
            _infoRow('Rol', _user?.role),
            const Divider(),
            _infoRow('Verificado', _user?.isVerified ? 'Sí' : 'No'),
          ],
        ),
      ),
    );
  }

  Widget _infoRow(String label, String? value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: AppTheme.textSecondary)),
          Text(value ?? '-', style: const TextStyle(fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }

  Widget _buildDriverSection() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Métodos de pago aceptados',
                style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            if (_acceptedPayments.isEmpty)
              const Text('Ninguno configurado',
                  style: TextStyle(color: AppTheme.textSecondary))
            else
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: _acceptedPayments
                    .map((p) => Chip(label: Text(p)))
                    .toList(),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildActionsSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OutlinedButton.icon(
          onPressed: () => context.push('/profile/edit'),
          icon: const Icon(Icons.edit),
          label: const Text('Editar Perfil'),
        ),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: () => context.push('/profile/password'),
          icon: const Icon(Icons.lock),
          label: const Text('Cambiar Contraseña'),
        ),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: () => context.push('/history'),
          icon: const Icon(Icons.history),
          label: const Text('Historial de Viajes'),
        ),
      ],
    );
  }
}
