import 'package:flutter/material.dart';
import 'app/theme.dart';
import 'app/router.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const VanAppRoot());
}

class VanAppRoot extends StatelessWidget {
  const VanAppRoot({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'VAN',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      routerConfig: VanApp.router,
    );
  }
}
