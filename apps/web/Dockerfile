FROM node:26-alpine

WORKDIR /app

COPY apps/web/package.json ./
RUN npm install --package-lock-only 2>/dev/null || true
RUN npm ci --ignore-scripts 2>/dev/null || npm install

COPY apps/web ./

# Drop root: the image ships a non-privileged `node` user.
RUN chown -R node:node /app
USER node

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
