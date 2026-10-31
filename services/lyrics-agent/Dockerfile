FROM node:22-bookworm-slim

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev

COPY src ./src
RUN mkdir -p /tmp/ragam-lyrics-workspace

ENV PORT=8020
EXPOSE 8020

CMD ["npm", "start"]
