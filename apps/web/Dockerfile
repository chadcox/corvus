FROM node:26-alpine

WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --ignore-scripts

COPY apps/web ./

# Drop root: the image ships a non-privileged `node` user.
RUN chown -R node:node /app
USER node

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
