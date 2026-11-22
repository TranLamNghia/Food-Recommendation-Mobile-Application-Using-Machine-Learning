using System.ComponentModel.DataAnnotations;
using Api.Planning;

namespace Api.Feedback;

/// <summary>§7.8.1 — rate a dish after eating it.</summary>
public sealed class CreateFeedbackRequest
{
    [Required(ErrorMessage = "Thiếu mã món ăn")]
    public string? FoodId { get; init; }

    [Required(ErrorMessage = "Thiếu số sao")]
    [Range(1, 5, ErrorMessage = "Số sao phải từ 1 đến 5")]
    public int? Rating { get; init; }

    /// <summary>
    /// Characters, not bytes — the column is <c>TEXT</c> and the limit is
    /// §7.8.1's, for the person writing rather than for the storage.
    /// </summary>
    [StringLength(1000, ErrorMessage = "Nhận xét tối đa 1000 ký tự")]
    public string? Comment { get; init; }
}

public sealed class FeedbackResponse
{
    public string Id { get; init; } = string.Empty;
    public string FoodId { get; init; } = string.Empty;
    public string FoodName { get; init; } = string.Empty;
    public int Rating { get; init; }
    public string? Comment { get; init; }
    public DateTime CreatedAt { get; init; }

    /// <summary>
    /// Whether the preference vector was rebuilt from this rating before the
    /// response was sent.
    ///
    /// <para><c>false</c> does not mean the rating was lost — it is stored
    /// either way, and §7.8.1 answers <c>201</c> either way. It means the ML
    /// service did not answer, so the next plan is built from the vector as
    /// it was. The rating is in the database and the next rebuild picks it
    /// up.</para>
    /// </summary>
    public bool ProfileUpdated { get; init; }
}

/// <summary>§7.8.2 — the ratings this user has sent.</summary>
public sealed class FeedbackPageResponse
{
    public List<FeedbackItemDto> Items { get; init; } = [];
    public int Page { get; init; }
    public int PageSize { get; init; }
    public int TotalItems { get; init; }
    public int TotalPages { get; init; }
}

public sealed class FeedbackItemDto
{
    public string Id { get; init; } = string.Empty;

    /// <summary>The same brief §7.6.1 and §7.7.1 send.</summary>
    public FoodBriefDto Food { get; init; } = new();

    public int Rating { get; init; }
    public string? Comment { get; init; }
    public DateTime CreatedAt { get; init; }
}
