import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../app/theme.dart';
import '../../core/services/wallet_service.dart';
import '../../core/models/wallet.dart';

class WalletScreen extends StatefulWidget {
  const WalletScreen({super.key});
  @override
  State<WalletScreen> createState() => _WalletScreenState();
}

class _WalletScreenState extends State<WalletScreen> {
  final _walletService = WalletService();
  Wallet? _wallet;
  List<WalletTransaction> _transactions = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    final wallet = await _walletService.getWallet();
    final txs = await _walletService.getTransactions();
    if (mounted) {
      setState(() {
        _wallet = wallet;
        _transactions = txs;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Billetera')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _loadData,
              child: ListView(
                padding: const EdgeInsets.all(20),
                children: [
                  _buildBalanceCard(),
                  const SizedBox(height: 24),
                  Row(
                    children: [
                      Expanded(
                        child: ElevatedButton.icon(
                          onPressed: () => _showTopUpDialog('mercadopago'),
                          icon: const Icon(Icons.payment),
                          label: const Text('Mercado Pago'),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: () => _showTopUpDialog('cvu'),
                          icon: const Icon(Icons.account_balance),
                          label: const Text('Transferencia'),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),
                  const Text('Movimientos',
                      style:
                          TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 12),
                  if (_transactions.isEmpty)
                    const Center(
                      child: Padding(
                        padding: EdgeInsets.all(32),
                        child: Text('Sin movimientos',
                            style: TextStyle(color: AppTheme.textSecondary)),
                      ),
                    )
                  else
                    ..._transactions.map(_buildTransactionTile),
                ],
              ),
            ),
    );
  }

  Widget _buildBalanceCard() {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [AppTheme.primary, Color(0xFF2D2D5E)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Saldo disponible',
              style: TextStyle(color: Colors.white70, fontSize: 14)),
          const SizedBox(height: 8),
          Text(
            '\$${(_wallet?.balance ?? 0).toStringAsFixed(2)}',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 36,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTransactionTile(WalletTransaction tx) {
    final isCredit = tx.type == 'credit' || tx.type == 'topup';
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: isCredit
            ? AppTheme.success.withOpacity(0.1)
            : AppTheme.error.withOpacity(0.1),
        child: Icon(
          isCredit ? Icons.arrow_downward : Icons.arrow_upward,
          color: isCredit ? AppTheme.success : AppTheme.error,
          size: 20,
        ),
      ),
      title: Text(tx.description ?? tx.type),
      subtitle: Text(
        tx.createdAt != null
            ? '${tx.createdAt!.day}/${tx.createdAt!.month}/${tx.createdAt!.year}'
            : '',
        style: const TextStyle(fontSize: 12),
      ),
      trailing: Text(
        '${isCredit ? '+' : '-'}\$${tx.amount.toStringAsFixed(0)}',
        style: TextStyle(
          fontWeight: FontWeight.bold,
          color: isCredit ? AppTheme.success : AppTheme.error,
        ),
      ),
    );
  }

  void _showTopUpDialog(String method) {
    final amountCtrl = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(method == 'mercadopago'
            ? 'Recargar con Mercado Pago'
            : 'Recargar por transferencia'),
        content: TextField(
          controller: amountCtrl,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
            labelText: 'Monto',
            prefixText: '\$ ',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancelar'),
          ),
          ElevatedButton(
            onPressed: () async {
              final amount = double.tryParse(amountCtrl.text);
              if (amount == null || amount < 100) return;
              Navigator.pop(ctx);
              final topup =
                  await _walletService.createTopUp(amount: amount, method: method);
              if (topup.initPoint != null && mounted) {
                // TODO: open init_point in WebView or redirect
              }
              await _loadData();
            },
            child: const Text('Recargar'),
          ),
        ],
      ),
    );
  }
}
