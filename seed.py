"""First-run seed data: 20+ realistic products and the admin user."""
import logging

from sqlalchemy import func, select

from auth import hash_password
from config import settings
from models import Product, User

logger = logging.getLogger("smartreco.seed")

SEED_PRODUCTS = [
    # ---------------- AI / ML ----------------
    dict(
        title="Machine Learning Foundations with Python",
        description=(
            "Build a rock-solid foundation in machine learning using Python, NumPy, and scikit-learn. "
            "You'll learn supervised and unsupervised learning, model evaluation, and feature engineering "
            "through hands-on projects with real datasets. By the end, you'll be able to train, tune, and "
            "explain your own ML models with confidence."
        ),
        category="AI/ML", price=49.99, difficulty_level="beginner",
        tags="python,machine-learning,scikit-learn,numpy,pandas",
        instructor_name="Dr. Elena Voss", duration_hours=12.5,
        thumbnail_url="https://images.unsplash.com/photo-1555255707-c07966088b7b?w=600",
    ),
    dict(
        title="Deep Learning with PyTorch: From Zero to Production",
        description=(
            "Master deep learning using PyTorch, covering neural networks, CNNs, RNNs, and transformers. "
            "This intermediate course focuses on practical implementation, taking you from a single "
            "perceptron to training and deploying production-grade models. Includes projects on image "
            "classification, sequence modeling, and model deployment with TorchServe."
        ),
        category="AI/ML", price=79.99, difficulty_level="intermediate",
        tags="pytorch,deep-learning,neural-networks,cnn,transformers",
        instructor_name="Marcus Chen", duration_hours=22.0,
        thumbnail_url="https://images.unsplash.com/photo-1620712943543-bcc4688e7485?w=600",
    ),
    dict(
        title="Advanced NLP: Building with Large Language Models",
        description=(
            "Go deep into transformer architectures, attention mechanisms, and fine-tuning large language "
            "models for real-world applications. You'll build retrieval-augmented generation pipelines, "
            "fine-tune open-source LLMs, and learn prompt engineering techniques used in production systems. "
            "Designed for engineers who already understand neural networks and want to specialize in NLP."
        ),
        category="AI/ML", price=99.99, difficulty_level="advanced",
        tags="nlp,llm,transformers,rag,prompt-engineering",
        instructor_name="Dr. Priya Raman", duration_hours=18.0,
        thumbnail_url="https://images.unsplash.com/photo-1677442136019-21780ecad995?w=600",
    ),
    dict(
        title="Computer Vision Bootcamp: OpenCV to Deep Learning",
        description=(
            "Learn computer vision from classical image processing with OpenCV through to modern deep "
            "learning approaches for object detection and segmentation. Hands-on projects include building "
            "a face detection pipeline, a real-time object tracker, and a custom image classifier deployed "
            "as a web API. Suited for learners with basic Python and ML experience."
        ),
        category="AI/ML", price=69.99, difficulty_level="intermediate",
        tags="computer-vision,opencv,deep-learning,object-detection",
        instructor_name="Dr. Elena Voss", duration_hours=16.5,
        thumbnail_url="https://images.unsplash.com/photo-1555949963-aa79dcee981c?w=600",
    ),
    dict(
        title="AI Agents and Autonomous Systems in Practice",
        description=(
            "Design and build autonomous AI agents that can plan, use tools, and reason over multi-step "
            "tasks. This advanced course covers agent architectures, function calling, memory systems, and "
            "multi-agent orchestration. You'll build a working autonomous research agent and a customer "
            "support agent as capstone projects."
        ),
        category="AI/ML", price=109.99, difficulty_level="advanced",
        tags="ai-agents,llm,autonomous-systems,function-calling",
        instructor_name="Marcus Chen", duration_hours=20.0,
        thumbnail_url="https://images.unsplash.com/photo-1485827404703-89b55fcc595e?w=600",
    ),

    # ---------------- Web Development ----------------
    dict(
        title="Modern JavaScript from the Ground Up",
        description=(
            "A complete introduction to JavaScript for absolute beginners, covering variables, functions, "
            "DOM manipulation, and asynchronous programming with promises and async/await. You'll build "
            "several small interactive projects along the way, including a to-do app and a weather widget. "
            "No prior programming experience required."
        ),
        category="Web Development", price=39.99, difficulty_level="beginner",
        tags="javascript,html,css,dom,async",
        instructor_name="Sarah Whitfield", duration_hours=14.0,
        thumbnail_url="https://images.unsplash.com/photo-1517180102446-f3ece451e9d8?w=600",
    ),
    dict(
        title="Full-Stack Development with React and Node.js",
        description=(
            "Build complete full-stack applications using React on the frontend and Node.js with Express "
            "on the backend, connected to a PostgreSQL database. Covers component architecture, state "
            "management, REST API design, and authentication. The capstone project is a fully functional "
            "social media application deployed to the cloud."
        ),
        category="Web Development", price=89.99, difficulty_level="intermediate",
        tags="react,nodejs,express,postgresql,full-stack",
        instructor_name="James Okafor", duration_hours=28.0,
        thumbnail_url="https://images.unsplash.com/photo-1633356122544-f134324a6cee?w=600",
    ),
    dict(
        title="Advanced React Patterns and Performance Optimization",
        description=(
            "Take your React skills to an expert level with advanced patterns like compound components, "
            "render props, custom hooks, and performance profiling. You'll learn to diagnose and fix "
            "re-render issues, implement code-splitting strategies, and build a design system used across "
            "multiple applications. Assumes solid working knowledge of React fundamentals."
        ),
        category="Web Development", price=94.99, difficulty_level="advanced",
        tags="react,performance,hooks,design-systems,frontend",
        instructor_name="Sarah Whitfield", duration_hours=15.0,
        thumbnail_url="https://images.unsplash.com/photo-1633356122102-3fe601e05bd2?w=600",
    ),
    dict(
        title="CSS Mastery: Grid, Flexbox, and Responsive Design",
        description=(
            "Master modern CSS layout techniques including Grid and Flexbox to build fully responsive, "
            "accessible websites without relying on frameworks. Covers animations, custom properties, and "
            "container queries with practical exercises rebuilding real website layouts. Great for "
            "beginners who already know basic HTML."
        ),
        category="Web Development", price=34.99, difficulty_level="beginner",
        tags="css,grid,flexbox,responsive-design,frontend",
        instructor_name="James Okafor", duration_hours=9.5,
        thumbnail_url="https://images.unsplash.com/photo-1507721999472-8ed4421c4af2?w=600",
    ),
    dict(
        title="GraphQL APIs: Design and Implementation",
        description=(
            "Learn to design and build production-grade GraphQL APIs using Apollo Server and TypeScript. "
            "Covers schema design, resolvers, authentication, N+1 query optimization with DataLoader, and "
            "subscriptions for real-time features. Includes a full project building a GraphQL layer over an "
            "existing REST backend."
        ),
        category="Web Development", price=74.99, difficulty_level="intermediate",
        tags="graphql,apollo,typescript,api-design",
        instructor_name="Nina Kowalski", duration_hours=13.0,
        thumbnail_url="https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=600",
    ),

    # ---------------- Data Science ----------------
    dict(
        title="Data Analysis with Python and Pandas",
        description=(
            "Learn to clean, transform, and analyze real-world datasets using Python's Pandas library. "
            "This beginner-friendly course covers data wrangling, exploratory data analysis, and building "
            "your first visualizations with Matplotlib and Seaborn. Includes a capstone project analyzing a "
            "public dataset end to end."
        ),
        category="Data Science", price=44.99, difficulty_level="beginner",
        tags="python,pandas,data-analysis,eda,visualization",
        instructor_name="Dr. Amara Osei", duration_hours=11.0,
        thumbnail_url="https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=600",
    ),
    dict(
        title="Statistics and Probability for Data Scientists",
        description=(
            "Build the statistical foundation every data scientist needs, covering probability "
            "distributions, hypothesis testing, confidence intervals, and regression analysis with "
            "practical Python implementations. Designed to bridge the gap between theory and the everyday "
            "reality of analyzing messy data. Some basic Python knowledge is helpful but not required."
        ),
        category="Data Science", price=54.99, difficulty_level="intermediate",
        tags="statistics,probability,hypothesis-testing,regression",
        instructor_name="Dr. Amara Osei", duration_hours=17.0,
        thumbnail_url="https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=600",
    ),
    dict(
        title="Data Engineering with Apache Spark and Airflow",
        description=(
            "Design and build scalable data pipelines using Apache Spark for distributed processing and "
            "Airflow for orchestration. Covers batch and streaming architectures, data quality checks, and "
            "deploying pipelines to production. Intended for engineers who want to move from analytics into "
            "large-scale data infrastructure work."
        ),
        category="Data Science", price=99.99, difficulty_level="advanced",
        tags="spark,airflow,data-engineering,etl,big-data",
        instructor_name="Viktor Petrov", duration_hours=24.0,
        thumbnail_url="https://images.unsplash.com/photo-1504868584819-f8e8b4b6d7e3?w=600",
    ),
    dict(
        title="Data Visualization Storytelling with Tableau",
        description=(
            "Learn to turn raw data into compelling visual stories using Tableau, covering dashboard "
            "design, chart selection, and interactivity best practices. You'll build a portfolio of "
            "dashboards covering sales, marketing, and operations use cases. No coding experience needed, "
            "just a willingness to think visually about data."
        ),
        category="Data Science", price=42.99, difficulty_level="beginner",
        tags="tableau,data-visualization,dashboards,storytelling",
        instructor_name="Nina Kowalski", duration_hours=8.5,
        thumbnail_url="https://images.unsplash.com/photo-1543286386-713bdd548da4?w=600",
    ),
    dict(
        title="Time Series Forecasting for Business Analytics",
        description=(
            "Master time series analysis and forecasting techniques including ARIMA, Prophet, and "
            "LSTM-based models applied to real business problems like demand forecasting and financial "
            "prediction. Covers seasonality decomposition, model evaluation, and building forecasting "
            "pipelines that run reliably in production. Assumes intermediate Python and statistics knowledge."
        ),
        category="Data Science", price=79.99, difficulty_level="advanced",
        tags="time-series,forecasting,arima,prophet,lstm",
        instructor_name="Dr. Amara Osei", duration_hours=15.5,
        thumbnail_url="https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?w=600",
    ),

    # ---------------- DevOps ----------------
    dict(
        title="Docker and Containers for Beginners",
        description=(
            "Get hands-on with Docker fundamentals, learning to build, run, and manage containers for your "
            "applications. Covers Dockerfiles, images, volumes, networking, and Docker Compose for "
            "multi-container applications. Perfect for developers who want to understand modern deployment "
            "workflows from the ground up."
        ),
        category="DevOps", price=44.99, difficulty_level="beginner",
        tags="docker,containers,devops,docker-compose",
        instructor_name="Tomasz Nowak", duration_hours=10.0,
        thumbnail_url="https://images.unsplash.com/photo-1605745341112-85968b19335b?w=600",
    ),
    dict(
        title="Kubernetes in Production: Deployment and Scaling",
        description=(
            "Learn to deploy, scale, and operate Kubernetes clusters running real production workloads. "
            "Covers pods, deployments, services, ingress, autoscaling, and observability with Prometheus "
            "and Grafana. Includes a full project deploying a microservices application with zero-downtime "
            "rolling updates. Requires basic Docker knowledge."
        ),
        category="DevOps", price=94.99, difficulty_level="intermediate",
        tags="kubernetes,devops,scaling,prometheus,microservices",
        instructor_name="Tomasz Nowak", duration_hours=20.0,
        thumbnail_url="https://images.unsplash.com/photo-1667372393119-3d4c48d07fc9?w=600",
    ),
    dict(
        title="CI/CD Pipelines with GitHub Actions",
        description=(
            "Build robust continuous integration and deployment pipelines using GitHub Actions, covering "
            "automated testing, build matrices, secrets management, and multi-environment deployments. "
            "You'll set up a complete pipeline that tests, builds, and deploys a real application on every "
            "push. Great for teams looking to automate their release process."
        ),
        category="DevOps", price=54.99, difficulty_level="intermediate",
        tags="ci-cd,github-actions,automation,devops",
        instructor_name="Rachel Kim", duration_hours=9.0,
        thumbnail_url="https://images.unsplash.com/photo-1667372393119-8f0e6cddc4f0?w=600",
    ),
    dict(
        title="Infrastructure as Code with Terraform",
        description=(
            "Master infrastructure as code using Terraform to provision and manage cloud resources across "
            "AWS, Azure, and GCP in a repeatable, version-controlled way. Covers modules, state management, "
            "and multi-environment workflows used by real platform teams. Assumes familiarity with at least "
            "one cloud provider."
        ),
        category="DevOps", price=89.99, difficulty_level="advanced",
        tags="terraform,infrastructure-as-code,aws,cloud",
        instructor_name="Viktor Petrov", duration_hours=16.0,
        thumbnail_url="https://images.unsplash.com/photo-1667372459736-5eb4e0b3f5e6?w=600",
    ),
    dict(
        title="Site Reliability Engineering Fundamentals",
        description=(
            "Learn the principles of SRE including SLOs, error budgets, incident response, and building "
            "resilient systems at scale. Covers observability, on-call practices, and post-mortem culture "
            "drawn from real production incidents. Designed for engineers moving into platform and "
            "reliability-focused roles."
        ),
        category="DevOps", price=84.99, difficulty_level="advanced",
        tags="sre,reliability,observability,incident-response",
        instructor_name="Rachel Kim", duration_hours=14.0,
        thumbnail_url="https://images.unsplash.com/photo-1518770660439-4636190af475?w=600",
    ),

    # ---------------- Mobile Development ----------------
    dict(
        title="iOS App Development with Swift and SwiftUI",
        description=(
            "Build your first iOS applications from scratch using Swift and SwiftUI, covering layouts, "
            "navigation, state management, and connecting to REST APIs. You'll design and ship a complete "
            "portfolio app to the App Store by the end of the course. No prior mobile development experience "
            "required."
        ),
        category="Mobile Development", price=64.99, difficulty_level="beginner",
        tags="ios,swift,swiftui,mobile",
        instructor_name="Daniel Ferreira", duration_hours=18.0,
        thumbnail_url="https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?w=600",
    ),
    dict(
        title="Cross-Platform Apps with React Native",
        description=(
            "Learn to build native mobile apps for iOS and Android from a single React Native codebase. "
            "Covers navigation, native modules, animations, and publishing to both app stores. Includes a "
            "capstone project building a full-featured social app with offline support. Requires basic "
            "React knowledge."
        ),
        category="Mobile Development", price=79.99, difficulty_level="intermediate",
        tags="react-native,mobile,cross-platform,ios,android",
        instructor_name="Daniel Ferreira", duration_hours=21.0,
        thumbnail_url="https://images.unsplash.com/photo-1607252650355-f7fd0460ccdb?w=600",
    ),
    dict(
        title="Android Development with Kotlin and Jetpack Compose",
        description=(
            "Master modern Android development using Kotlin and Jetpack Compose, covering declarative UI, "
            "ViewModels, coroutines, and Room database integration. Build a production-quality note-taking "
            "app with offline sync and a polished Material Design interface. Assumes basic programming "
            "experience."
        ),
        category="Mobile Development", price=69.99, difficulty_level="intermediate",
        tags="android,kotlin,jetpack-compose,mobile",
        instructor_name="Leah Bennett", duration_hours=19.5,
        thumbnail_url="https://images.unsplash.com/photo-1607252651386-c93c2ac9f5e1?w=600",
    ),
    dict(
        title="Advanced Mobile Architecture and Performance Tuning",
        description=(
            "Dive deep into advanced mobile architecture patterns like MVVM and Clean Architecture, along "
            "with performance profiling and memory optimization techniques for both iOS and Android. "
            "You'll refactor a poorly-performing app into a fast, maintainable codebase while learning to "
            "diagnose jank, memory leaks, and slow startup times. For experienced mobile developers."
        ),
        category="Mobile Development", price=99.99, difficulty_level="advanced",
        tags="mobile-architecture,performance,mvvm,clean-architecture",
        instructor_name="Leah Bennett", duration_hours=17.0,
        thumbnail_url="https://images.unsplash.com/photo-1526498460520-4c246339dccb?w=600",
    ),
    dict(
        title="Flutter for Beginners: Build Your First App",
        description=(
            "Get started with Flutter and Dart to build beautiful, natively-compiled mobile apps from a "
            "single codebase. Covers widgets, state management with Provider, and integrating with Firebase "
            "for authentication and storage. Ends with a fully working expense tracker app ready to publish."
        ),
        category="Mobile Development", price=49.99, difficulty_level="beginner",
        tags="flutter,dart,mobile,firebase",
        instructor_name="Daniel Ferreira", duration_hours=13.5,
        thumbnail_url="https://images.unsplash.com/photo-1512941937669-90a1b58e7e9c?w=600",
    ),
]


async def seed_products_if_empty(db):
    count = (await db.execute(select(func.count(Product.id)))).scalar_one()
    if count > 0:
        logger.info("Products table already has %d rows, skipping seed", count)
        return

    logger.info("Seeding %d products...", len(SEED_PRODUCTS))
    products = [Product(**data) for data in SEED_PRODUCTS]
    db.add_all(products)
    await db.commit()

    for p in products:
        await db.refresh(p)

    import vector_store

    for product in products:
        await vector_store.upsert_product(product)

    logger.info("Product seed complete (%d products written to SQL + ChromaDB)", len(products))


async def seed_admin_if_missing(db):
    admin = (await db.execute(select(User).where(User.is_admin.is_(True)))).scalar_one_or_none()
    if admin is not None:
        return

    existing = (await db.execute(select(User).where(User.email == settings.ADMIN_EMAIL))).scalar_one_or_none()
    if existing is not None:
        existing.is_admin = True
        await db.commit()
        logger.info("Promoted existing user %s to admin", settings.ADMIN_EMAIL)
        return

    admin_user = User(
        email=settings.ADMIN_EMAIL,
        hashed_password=hash_password(settings.ADMIN_PASSWORD),
        full_name="Admin",
        is_admin=True,
        is_active=True,
    )
    db.add(admin_user)
    await db.commit()
    logger.info("Created admin user %s", settings.ADMIN_EMAIL)
