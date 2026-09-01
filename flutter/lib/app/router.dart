import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../features/auth/login_screen.dart';
import '../features/auth/register_screen.dart';
import '../features/passenger/passenger_home.dart';
import '../features/passenger/request_trip_screen.dart';
import '../features/trip/active_trip_screen.dart';
import '../features/trip/rate_trip_screen.dart';
import '../features/driver/driver_home_screen.dart';
import '../features/driver/driver_trip_screen.dart';
import '../features/wallet/wallet_screen.dart';
import '../features/profile/profile_screen.dart';
import '../features/history/history_screen.dart';

class VanApp {
  VanApp._();

  static final GoRouter router = GoRouter(
    initialLocation: '/login',
    routes: [
      GoRoute(
        path: '/login',
        builder: (_, __) => const LoginScreen(),
      ),
      GoRoute(
        path: '/register',
        builder: (_, __) => const RegisterScreen(),
      ),
      GoRoute(
        path: '/home',
        builder: (_, __) => const PassengerHomeScreen(),
      ),
      GoRoute(
        path: '/passenger/request',
        builder: (_, __) => const RequestTripScreen(),
      ),
      GoRoute(
        path: '/trip/active',
        builder: (_, __) => const ActiveTripScreen(),
      ),
      GoRoute(
        path: '/trip/rate/:tripId',
        builder: (_, state) {
          final tripId = int.parse(state.pathParameters['tripId']!);
          return RateTripScreen(tripId: tripId);
        },
      ),
      GoRoute(
        path: '/driver',
        builder: (_, __) => const DriverHomeScreen(),
      ),
      GoRoute(
        path: '/driver/trip/:tripId',
        builder: (_, state) {
          final tripId = int.parse(state.pathParameters['tripId']!);
          return DriverTripScreen(tripId: tripId);
        },
      ),
      GoRoute(
        path: '/wallet',
        builder: (_, __) => const WalletScreen(),
      ),
      GoRoute(
        path: '/profile',
        builder: (_, __) => const ProfileScreen(),
      ),
      GoRoute(
        path: '/history',
        builder: (_, __) => const HistoryScreen(),
      ),
    ],
  );
}
