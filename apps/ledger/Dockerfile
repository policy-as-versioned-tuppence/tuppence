FROM maven:3.9-eclipse-temurin-11 AS build
WORKDIR /app
COPY pom.xml .
COPY src ./src
RUN mvn -q -B package

FROM eclipse-temurin:11-jre-alpine
COPY --from=build /app/target/ledger.jar /app/ledger.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/ledger.jar"]
