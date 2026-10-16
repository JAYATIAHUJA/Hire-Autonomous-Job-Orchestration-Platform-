"""Scikit-learn model trainer for Ghost Job classification.

Trains Logistic Regression and Random Forest classifiers on labeled hiring datasets,
evaluates precision/recall/ROC-AUC, and exports calibrated beta coefficients.
"""

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score
from sklearn.model_selection import train_test_split

from .features import extract_features


def generate_synthetic_benchmark_dataset() -> tuple[np.ndarray, np.ndarray]:
    """Generates a diverse benchmark dataset of genuine vs ghost job postings."""
    samples = []
    labels = []  # 1 = Legitimate, 0 = Ghost

    # 1. High Legitimacy Postings: Fresh, high specificity, salary disclosed, no layoffs
    legit_templates = [
        ("Swiggy", "swiggy.com", False, "Backend Engineer with Python FastAPI, PostgreSQL, Redis and Kafka", "₹14 LPA - ₹20 LPA", 7, 0),
        ("Zepto", "zeptonow.com", False, "Frontend Developer with React 18, TypeScript, Tailwind and Next.js", "₹10 LPA - ₹15 LPA", 12, 0),
        ("CRED", "cred.club", False, "Android Developer proficient in Kotlin, Jetpack Compose and Coroutines", "₹18 LPA - ₹26 LPA", 4, 0),
        ("Razorpay", "razorpay.com", False, "SDE-1 Golang backend, microservices, gRPC, Docker, MySQL", "₹15 LPA - ₹22 LPA", 10, 0),
        ("Zomato", "zomato.com", False, "Data Engineer with Python, Spark, Snowflake, Airflow and SQL", "₹12 LPA - ₹18 LPA", 15, 0),
        ("PhonePe", "phonepe.com", False, "Platform Engineer with Kubernetes, Terraform, AWS, Linux, CI/CD", "₹16 LPA - ₹24 LPA", 8, 0),
    ]

    # 2. Moderate Postings: Minor age gaps (30-50 days) or missing explicit compensation
    moderate_templates = [
        ("Tech Mahindra", "techmahindra.com", False, "Java Developer with Spring Boot and Oracle database", None, 35, 1),
        ("Infosys", "infosys.com", False, "Full Stack Developer Angular and Node.js enterprise portal", None, 42, 1),
        ("TCS", "tcs.com", False, "Python automation tester with PyTest and Selenium", "Industry standard", 28, 0),
        ("Wipro", "wipro.com", False, "React Native mobile engineer with Redux state management", None, 45, 1),
    ]

    # 3. High-Risk Ghost Postings: > 60-120 days old, repeatedly reposted, vague buzzwords, downsizing
    ghost_templates = [
        ("Apex Edtech", "apex-edtech-layoff.com", True, "Rockstar ninja developer to wear multiple hats in fast-paced startup", None, 85, 4),
        ("TalentPool Staffing", "talentpool-harvest.io", False, "Continuous talent pipeline drive for upcoming enterprise client needs", None, 110, 6),
        ("Global Corp", "unacademy.com", True, "Urgent dynamic self-starter to drive synergies across business units", "Best in industry", 75, 3),
        ("Byju Tech", "byjus.com", True, "General software engineer to handle various ad-hoc engineering challenges", None, 95, 5),
        ("Staffing Agency X", "harvest-resumes.biz", False, "Submit your CV for future placement drives in multinational corporations", None, 120, 8),
        ("Phantom Labs", "phantom-corp.net", False, "High-octane rockstar guru to take ownership end-to-end hustle", None, 90, 4),
    ]

    # Expand templates with minor variations for training
    for comp, dom, lay, desc, sal, age, rep in legit_templates * 8:
        jitter_age = max(1, age + int(np.random.randint(-3, 8)))
        feat = extract_features(
            posting_age_days=jitter_age,
            repost_count=rep,
            raw_description=desc,
            salary_range=sal,
            company_name=comp,
            company_domain=dom,
            external_layoff_flag=lay,
        )
        samples.append(feat.to_feature_vector())
        labels.append(1)

    for comp, dom, lay, desc, sal, age, rep in moderate_templates * 8:
        jitter_age = max(15, age + int(np.random.randint(-5, 10)))
        feat = extract_features(
            posting_age_days=jitter_age,
            repost_count=rep,
            raw_description=desc,
            salary_range=sal,
            company_name=comp,
            company_domain=dom,
            external_layoff_flag=lay,
        )
        samples.append(feat.to_feature_vector())
        labels.append(1 if jitter_age < 40 else 0)

    for comp, dom, lay, desc, sal, age, rep in ghost_templates * 8:
        jitter_age = max(60, age + int(np.random.randint(-5, 20)))
        feat = extract_features(
            posting_age_days=jitter_age,
            repost_count=max(2, rep + int(np.random.randint(0, 3))),
            raw_description=desc,
            salary_range=sal,
            company_name=comp,
            company_domain=dom,
            external_layoff_flag=lay,
        )
        samples.append(feat.to_feature_vector())
        labels.append(0)

    return np.array(samples), np.array(labels)


def train_and_evaluate_models() -> dict[str, float]:
    """Train Logistic Regression and Random Forest classifiers and return performance metrics."""
    X, y = generate_synthetic_benchmark_dataset()
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)

    # 1. Logistic Regression
    lr = LogisticRegression(class_weight="balanced", random_state=42)
    lr.fit(X_train, y_train)
    lr_preds = lr.predict(X_test)
    lr_proba = lr.predict_proba(X_test)[:, 1]

    # 2. Random Forest
    rf = RandomForestClassifier(n_estimators=50, max_depth=4, random_state=42)
    rf.fit(X_train, y_train)
    rf_preds = rf.predict(X_test)
    rf_proba = rf.predict_proba(X_test)[:, 1]

    return {
        "lr_accuracy": float(accuracy_score(y_test, lr_preds)),
        "lr_roc_auc": float(roc_auc_score(y_test, lr_proba)),
        "rf_accuracy": float(accuracy_score(y_test, rf_preds)),
        "rf_roc_auc": float(roc_auc_score(y_test, rf_proba)),
        "lr_intercept": float(lr.intercept_[0]),
        "lr_coefficients": [float(c) for c in lr.coef_[0]],
    }


if __name__ == "__main__":
    results = train_and_evaluate_models()
    print("=== Ghost Job ML Model Training Results ===")
    print(f"Logistic Regression ROC-AUC: {results['lr_roc_auc']:.3f} | Accuracy: {results['lr_accuracy']:.3f}")
    print(f"Random Forest ROC-AUC:       {results['rf_roc_auc']:.3f} | Accuracy: {results['rf_accuracy']:.3f}")
    print(f"Trained Intercept: {results['lr_intercept']:.3f}")
    print(f"Trained Coefficients: {results['lr_coefficients']}")
