import '../styles/components/StructuredMessage.css'

/**
 * SkeletonTopicCard — shimmer placeholder shown while AI is thinking.
 * Mimics the TopicCard layout with animated gradient lines.
 */
function SkeletonTopicCard() {
  return (
    <div className="skeleton-card" aria-hidden="true">
      <div className="skeleton-card__header">
        <div className="skeleton-card__icon shimmer" />
        <div className="skeleton-card__title-group">
          <div className="skeleton-card__title shimmer" />
          <div className="skeleton-card__subtitle shimmer" />
        </div>
      </div>
      <div className="skeleton-card__body">
        <div className="skeleton-card__stop">
          <div className="skeleton-card__time shimmer" />
          <div className="skeleton-card__line shimmer" />
        </div>
        <div className="skeleton-card__stop">
          <div className="skeleton-card__time shimmer" />
          <div className="skeleton-card__line shimmer" />
        </div>
        <div className="skeleton-card__stop">
          <div className="skeleton-card__time shimmer" />
          <div className="skeleton-card__line--short shimmer" />
        </div>
      </div>
    </div>
  )
}

/**
 * SkeletonLoading — renders 2 skeleton cards to fill the loading state.
 */
export function SkeletonLoading() {
  return (
    <div className="skeleton-loading">
      <div className="skeleton-loading__lead shimmer" />
      <SkeletonTopicCard />
      <SkeletonTopicCard />
    </div>
  )
}

export default SkeletonTopicCard
