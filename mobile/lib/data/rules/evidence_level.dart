/// How much a nutrition threshold can be trusted — the
/// `condition_rules.evidence_level` column.
///
/// It exists because a health app quoting a WHO recommendation and a number
/// nobody has checked in the **same voice** is not honest. The provenance of
/// every threshold used to live in the prose of the `note` column, so
/// classifying one meant searching for the string "chưa xác minh" inside a
/// sentence — which breaks the first time anybody edits the wording.
///
/// Four levels, not three: see [definitional].
///
/// Note on language: `code` is the value stored in the database and `label`
/// is the short phrase shown on screen, so both stay as they are.
enum EvidenceLevel {
  /// The rule **IS** the definition; there is no threshold to cite.
  ///
  /// "If you are allergic to eggs, drop dishes containing egg" needs no
  /// organisation to publish it. Every tag rule belongs to this group — 9 of
  /// 20 rules. Forcing them into [published] would amount to claiming
  /// somebody published the obvious.
  definitional('definitional', 'quy tắc định nghĩa'),

  /// The number is taken verbatim from a source that is **still in force**.
  ///
  /// WHO: sodium under 2 000 mg/day. The Japanese gout guideline: purine
  /// under 400 mg/day. This is the only level that may be quoted as a sourced
  /// recommendation.
  published('published', 'có nguồn công bố'),

  /// The source is real but the number is a **derivation**, so it only holds
  /// together with the assumption attached to it.
  ///
  /// KDIGO's 48 g of protein is right for a 60 kg person, not for a 90 kg
  /// one; 25 g of sugar is 5 % of a 2 000 kcal diet; total fat stands in for
  /// saturated fat because the composition table does not separate them.
  derived('derived', 'suy ra kèm giả thiết'),

  /// There is **no source still in force**.
  ///
  /// Two different situations land here, and `note` tells them apart: the
  /// 300 mg/day cholesterol threshold was **withdrawn** from the Dietary
  /// Guidelines 2015 and AHA/ACC 2019; the 500 mg sodium threshold for the
  /// severe level has **never** been checked by anyone. For presentation
  /// purposes the two are the same — neither may be quoted as a
  /// recommendation.
  unsupported('unsupported', 'không có nguồn đang hiệu lực');

  const EvidenceLevel(this.code, this.label);

  /// The value in the database.
  final String code;

  /// A short phrase for the interface.
  final String label;

  /// Whether this threshold may be quoted as a sourced recommendation.
  ///
  /// Only [published]. [derived] comes with an assumption attached so it may
  /// not, [unsupported] has no source at all, and [definitional] has no
  /// threshold to quote.
  bool get canCite => this == EvidenceLevel.published;

  /// Reads the level from the code in the database.
  ///
  /// An unrecognised code returns [derived] — a level that **cannot** be
  /// quoted as sourced. Returning [published] for an unrecognised code would
  /// let a bad value claim to have a source, exactly the failure to avoid
  /// here.
  static EvidenceLevel fromCode(String? code) => switch (code) {
    'definitional' => EvidenceLevel.definitional,
    'published' => EvidenceLevel.published,
    'unsupported' => EvidenceLevel.unsupported,
    _ => EvidenceLevel.derived,
  };
}
