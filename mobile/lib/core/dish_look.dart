import 'package:flutter/material.dart';

// `DishRole` lives beside `Food`. Imported for the enum only — this file
// is a UI one, so depending on the model that carries Flutter colours
// costs nothing here.
import '../data/models/food.dart';
import '../data/models/food_brief.dart';

/// The colours and the icon a dish card is drawn with.
///
/// ## Why it is computed rather than stored
///
/// Every one of the 318 rows in `foods` has `image_url` **null**. There is no
/// photo set for Vietnamese dishes in this project and producing one is not a
/// thesis task, so a card has to be able to draw itself from nothing but the
/// dish's own data. It falls back to `dish_role`: deterministic, so the same
/// dish looks the same on every screen and on every launch, and honest,
/// because the role is the one thing about a dish that a colour can stand for
/// without inventing anything.
///
/// ## Why it is an extension and not a field
///
/// `FoodBrief` holds no `Color`, on purpose: `tool/smoke_api.dart` drives the
/// API layer with `dart run`, which compiles plain Dart and cannot see the
/// Flutter engine, so a single colour field in the data layer would take the
/// whole of it out of that tool's reach. Presentation lives here instead.
extension DishLook on FoodBrief {
  /// The icon shown when there is no photo.
  String get emoji => _lookFor(dishRole).emoji;

  /// The two-stop gradient behind the card.
  List<Color> get gradient => _lookFor(dishRole).gradient;
}

_RoleLook _lookFor(String dishRole) =>
    _byRole[DishRole.tryParse(dishRole)] ?? _byLabel[dishRole] ?? _fallback;

/// The gradient and icon one role falls back to.
class _RoleLook {
  const _RoleLook(this.emoji, this.gradient);

  final String emoji;
  final List<Color> gradient;
}

// The same pairs `MockFoods` assigns by hand, so a server-fed screen and a
// mock-fed one are the same application and not two.
const _warm = [Color(0xFFFFB884), Color(0xFFE87A3C)];
const _fresh = [Color(0xFF93DCA9), Color(0xFF3FA76F)];
const _broth = [Color(0xFFFFD68F), Color(0xFFE0A03E)];
const _sea = [Color(0xFF8FD1E8), Color(0xFF3C86B5)];
const _sweet = [Color(0xFFE7BCF2), Color(0xFFA55FC4)];
const _grain = [Color(0xFFF5DCA8), Color(0xFFC9A050)];

const _fallback = _RoleLook('🍽️', _grain);

/// Keyed on the `dish_role` ENUM code — what the server sends.
const Map<DishRole, _RoleLook> _byRole = {
  DishRole.main: _RoleLook('🍜', _broth),
  DishRole.sideProtein: _RoleLook('🍖', _warm),
  DishRole.sideVeg: _RoleLook('🥬', _fresh),
  DishRole.soup: _RoleLook('🍲', _fresh),
  DishRole.dessert: _RoleLook('🍧', _sweet),
  DishRole.drink: _RoleLook('🥤', _sea),
  DishRole.snack: _RoleLook('🥟', _grain),
};

/// Keyed on the Vietnamese label — what `MockFoods` stores in `dishRole`,
/// because the Dart copy of step 4 matches `MEAL_STRUCTURE` on those labels.
const Map<String, _RoleLook> _byLabel = {
  'Món chính': _RoleLook('🍜', _broth),
  'Món mặn': _RoleLook('🍖', _warm),
  'Món rau': _RoleLook('🥬', _fresh),
  'Món canh': _RoleLook('🍲', _fresh),
  'Món phụ': _RoleLook('🥟', _grain),
};
